# src/agent/session.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional
from pydantic import BaseModel, Field

from motor.motor_asyncio import AsyncIOMotorDatabase
from config.logging import get_logic_logger

from .types import ConversationHistory, Message


class Session(BaseModel):
    """
    会话实体 —— 纯内存对象，不绑定任何持久化逻辑。
    用 pydantic 统一序列化范式（和 Message 一致）。
    """

    session_id: str
    user_id: str  # 必填，消除权限模糊
    messages: List[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # ── 消息操作 ───────────────────────────────────────

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

    @property
    def preview(self) -> str:
        for msg in reversed(self.messages):
            if msg.content:
                return msg.content[:200]
        return ""

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def get_recent_messages(self, max_messages: int = 500) -> List[Message]:
        """获取最近 N 条消息，确保从 user 轮次开始。"""
        sliced = self.messages[-max_messages:]
        for i, m in enumerate(sliced):
            if m.role == "user":
                return sliced[i:]
        return sliced

    def to_history(self) -> ConversationHistory:
        history = ConversationHistory()
        for message in self.messages:
            history.add(message)
        return history



# ── 默认配置 ──────────────────────────────────────────
_DEFAULT_TTL_DAYS = 90
_DEFAULT_MAX_MESSAGES = 500


class SessionManager:
    """
    会话持久化管理器。

    存储设计：
    - agent_sessions: 会话元数据（轻量，用于列表查询）
    - agent_messages: 消息记录（增量写入，按 seq 排序）
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        *,
        ttl_days: int = _DEFAULT_TTL_DAYS,
        max_messages_per_session: int = _DEFAULT_MAX_MESSAGES,
    ) -> None:
        self.logger = get_logic_logger("session_manager")
        self._db = db
        self._sessions = db["agent_sessions"]
        self._messages = db["agent_messages"]
        self._ttl_days = ttl_days
        self._max_messages = max_messages_per_session
        self._indexes_ensured = False

    # ── 索引 ──────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """确保索引存在（幂等，应用启动时调用一次）。"""
        if self._indexes_ensured:
            return

        # 会话表
        await self._sessions.create_index(
            [("session_id", 1), ("user_id", 1)],
            unique=True,
            name="ux_session_user",
        )
        await self._sessions.create_index(
            [("user_id", 1), ("updated_at", -1)],
            name="ix_user_updated",
        )
        await self._sessions.create_index(
            "expires_at",
            expireAfterSeconds=0,
            name="ttl_expires",
        )

        # 消息表
        await self._messages.create_index(
            [("session_id", 1), ("seq", 1)],
            unique=True,
            name="ux_session_seq",
        )

        self._indexes_ensured = True
        self.logger.info("session_indexes_ensured")

    # ── CRUD ──────────────────────────────────────────

    async def get_or_create(self, session_id: str, user_id: str) -> Session:
        session = await self.load(session_id, user_id)
        if session is not None:
            return session
        return Session(session_id=session_id, user_id=user_id)

    async def load(self, session_id: str, user_id: str) -> Optional[Session]:
        """加载会话（元数据 + 消息）。"""
        meta = await self._sessions.find_one(
            {"session_id": session_id, "user_id": user_id}
        )
        if meta is None:
            return None

        # 只加载最近 N 条消息
        cursor = (
            self._messages.find({"session_id": session_id})
            .sort("seq", 1)
            .limit(self._max_messages)
        )
        raw_messages = await cursor.to_list(length=self._max_messages)
        messages = [Message.model_validate(m) for m in raw_messages]

        return Session(
            session_id=session_id,
            user_id=user_id,
            messages=messages,
            created_at=meta.get("created_at", datetime.now(timezone.utc)),
            updated_at=meta.get("updated_at", datetime.now(timezone.utc)),
            metadata=meta.get("metadata", {}),
        )

    async def save(self, session: Session) -> None:
        """
        保存会话：
        1. upsert 元数据文档
        2. 增量写入新消息（基于 seq 去重）
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self._ttl_days)

        # ── 1. 获取当前最大 seq ──
        last_msg = await self._messages.find_one(
            {"session_id": session.session_id},
            sort=[("seq", -1)],
            projection={"seq": 1},
        )
        existing_count = (last_msg["seq"] + 1) if last_msg else 0

        # ── 2. 找出新增的消息 ──
        new_messages = session.messages[existing_count:]

        if new_messages:
            docs = []
            for i, msg in enumerate(new_messages):
                doc = msg.model_dump(exclude_none=True)
                doc["session_id"] = session.session_id
                doc["user_id"] = session.user_id
                doc["seq"] = existing_count + i
                docs.append(doc)
            await self._messages.insert_many(docs, ordered=True)

        # ── 3. upsert 元数据 ──
        await self._sessions.update_one(
            {"session_id": session.session_id, "user_id": session.user_id},
            {
                "$set": {
                    "updated_at": now,
                    "preview": session.preview,
                    "message_count": existing_count + len(new_messages),
                    "metadata": session.metadata,
                    "expires_at": expires_at,
                },
                "$setOnInsert": {
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "created_at": session.created_at,
                },
            },
            upsert=True,
        )

    async def delete(self, session_id: str, user_id: str) -> None:
        """删除会话及其所有消息。"""
        await self._sessions.delete_one(
            {"session_id": session_id, "user_id": user_id}
        )
        await self._messages.delete_many({"session_id": session_id})

    # ── 查询 ──────────────────────────────────────────

    async def list_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的会话列表。
        只查元数据表，不读消息，O(1) 文档大小。
        """
        cursor = (
            self._sessions.find(
                {"user_id": user_id},
                projection={
                    "_id": 0,
                    "session_id": 1,
                    "updated_at": 1,
                    "preview": 1,
                    "message_count": 1,
                },
            )
            .sort("updated_at", -1)
        )
        docs = await cursor.to_list(length=200)
        return [
            {
                "thread_id": doc["session_id"],
                "last_updated": doc.get("updated_at", "").isoformat()
                    if hasattr(doc.get("updated_at"), "isoformat") else None,
                "preview": doc.get("preview", ""),
                "message_count": doc.get("message_count", 0),
            }
            for doc in docs
        ]

    async def get_messages(
        self,
        session_id: str,
        user_id: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """分页获取消息（支持懒加载）。"""
        # 先验证归属权
        meta = await self._sessions.find_one(
            {"session_id": session_id, "user_id": user_id},
            projection={"_id": 1},
        )
        if meta is None:
            return []

        cursor = (
            self._messages.find(
                {"session_id": session_id},
                projection={"_id": 0, "session_id": 0, "user_id": 0},
            )
            .sort("seq", 1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [
            {
                "role": doc.get("role"),
                "content": doc.get("content", ""),
                "created_at": doc.get("created_at", "").isoformat()
                    if hasattr(doc.get("created_at"), "isoformat") else None,
            }
            for doc in docs
        ]

    # ── 清理 ──────────────────────────────────────────

    async def cleanup_orphan_messages(self) -> int:
        """清理没有对应会话元数据的孤立消息（防御性维护）。"""
        session_ids = await self._sessions.distinct("session_id")
        result = await self._messages.delete_many(
            {"session_id": {"$nin": session_ids}}
        )
        return result.deleted_count

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from .models import MemoryItem, MemoryStatus, MemoryTier


class MemoryStoreFacade:
    """记忆存储门面，负责 Mongo 写入，LanceDB 同步由已有的同步服务完成。"""

    def __init__(
        self,
        mongo_collection: AsyncIOMotorCollection,
        lance_table: Any,
        embedding_fn: Callable[[str], Awaitable[List[float]]],
    ) -> None:
        self._mongo = mongo_collection
        self._lance = lance_table
        self._embedding_fn = embedding_fn

    async def add(self, item: MemoryItem) -> str:
        """写入记忆项到 MongoDB（LanceDB 由同步服务写入）。"""

        if item.embedding is None:
            item.embedding = await self._embedding_fn(item.content)
        await self._mongo.insert_one(item.to_dict())
        return item.memory_id

    async def search_semantic(
        self,
        query_embedding: List[float],
        tier: MemoryTier,
        user_id: Optional[str] = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        top_k: int = 10,
    ) -> List[MemoryItem]:
        """执行语义检索并回填完整记忆项。"""

        filter_expr = f"tier = '{tier.value}' AND status = '{status.value}'"
        if user_id:
            filter_expr = f"{filter_expr} AND user_id = '{user_id}'"

        query = await self._await_if_needed(self._lance.search(query_embedding))
        query = query.where(filter_expr).limit(top_k)
        lance_results = await self._await_if_needed(query.to_list())
        # print(f"[DEBUG] LanceDB search results: {lance_results}")
        ids = [r.get("memory_id") for r in lance_results if r.get("memory_id")]
        similarity_map: Dict[str, float] = {}
        for result in lance_results:
            memory_id = result.get("memory_id")
            if not memory_id:
                continue
            distance = result.get("distance", result.get("_distance", result.get("score")))
            if isinstance(distance, (int, float)):
                similarity_map[str(memory_id)] = 1.0 - float(distance)
        if not ids:
            return []

        cursor = self._mongo.find({"memory_id": {"$in": ids}})
        docs = await cursor.to_list(length=len(ids))
        item_map = {
            str(doc.get("memory_id")): MemoryItem.from_dict(doc) for doc in docs
        }
        ordered_items: List[MemoryItem] = []
        for memory_id in ids:
            item = item_map.get(memory_id)
            if item is None:
                continue
            similarity = similarity_map.get(memory_id)
            if similarity is not None:
                setattr(item, "similarity_score", similarity)
            ordered_items.append(item)
        return ordered_items

    async def update_status(
        self,
        memory_id: str,
        status: MemoryStatus,
        superseded_by: Optional[str] = None,
    ) -> None:
        """更新记忆项状态。"""

        update_doc: Dict[str, Any] = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }
        if superseded_by:
            update_doc["superseded_by"] = superseded_by
        await self._mongo.update_one({"memory_id": memory_id}, {"$set": update_doc})

    async def update(self, item: MemoryItem) -> None:
        """更新记忆项内容与向量。"""

        if item.embedding is None:
            item.embedding = await self._embedding_fn(item.content)
        item.updated_at = datetime.now(timezone.utc)
        await self._mongo.update_one(
            {"memory_id": item.memory_id},
            {"$set": item.to_dict()},
        )

    async def touch(self, memory_id: str) -> None:
        """更新访问时间与计数。"""

        await self._mongo.update_one(
            {"memory_id": memory_id},
            {
                "$set": {"last_accessed_at": datetime.now(timezone.utc)},
                "$inc": {"access_count": 1},
            },
        )

    async def get_user_memories(
        self,
        user_id: str,
        status: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> List[MemoryItem]:
        """获取用户记忆项。"""

        cursor = self._mongo.find(
            {
                "user_id": user_id,
                "status": status.value,
                "tier": MemoryTier.USER.value,
            }
        )
        docs = await cursor.to_list(length=None)
        return [MemoryItem.from_dict(doc) for doc in docs]

    async def get_agent_memories(
        self,
        status: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> List[MemoryItem]:
        """获取 Agent 记忆项。"""
        cursor = self._mongo.find(
            {
                "status": status.value,
                "tier": MemoryTier.AGENT.value,
            }
        )
        docs = await cursor.to_list(length=None)
        return [MemoryItem.from_dict(doc) for doc in docs]

    async def get_session_memories(self, session_id: str) -> List[MemoryItem]:
        """获取会话记忆项。"""

        cursor = self._mongo.find(
            {"session_id": session_id, "tier": MemoryTier.SESSION.value}
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=None)
        return [MemoryItem.from_dict(doc) for doc in docs]

    @staticmethod
    async def _await_if_needed(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from config.logging import get_service_logger, get_trace_id
from src.db.mongo_db import get_mongo_db
from src.async_worker.core import send_task
from src.models import TaskPriority, TaskSubType

from src.agent.lotus_agent import LotusAgent
from src.agent.session import SessionManager
from src.agent.types import Message, RequestContext, ToolCall, ToolFunctionCall


class ChatService:
    """
    业务编排层：
    - 会话 CRUD
    - 聊天流程编排（读 session → 调 agent → 写 session）
    - 流式/非流式分发
    """

    def __init__(
        self,
        agent: Optional[LotusAgent] = None,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.logger = get_service_logger("chat_service")
        self._agent = agent or LotusAgent()
        self._session_manager = session_manager
        self._session_manager_ready = False

    # ── 聊天 ─────────────────────────────────────────────

    async def chat_stream(
        self,
        query: str,
        user_id: str,
        thread_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式聊天：逐 token 返回事件，结束后持久化。"""
        session_manager = await self._get_session_manager()
        session = await session_manager.get_or_create(thread_id, user_id=user_id)
        await self._ensure_initial_memory_context(session, user_id)
        history = self._build_history_messages(session)
        session.add_message(Message(role="user", content=query))
        ctx = self._build_context(user_id, thread_id)

        chunks: List[str] = []
        async for event in self._agent.run(query=query, history=history, ctx=ctx):
            if event["type"] == "text_delta":
                chunk = str(event["data"].get("content") or "")
                if chunk:
                    chunks.append(chunk)
            elif event["type"] == "tool_start":
                data = event.get("data") or {}
                tool_call_id = str(data.get("tool_call_id") or "")
                tool_name = str(data.get("name") or "")
                tool_args = data.get("args") or {}
                if not isinstance(tool_args, dict):
                    tool_args = {"raw": tool_args}
                if tool_call_id and tool_name:
                    session.add_message(
                        Message(
                            role="assistant",
                            content=None,
                            tool_calls=[
                                ToolCall(
                                    id=tool_call_id,
                                    function=ToolFunctionCall(name=tool_name, arguments=tool_args),
                                )
                            ],
                        )
                    )
            elif event["type"] == "tool_end":
                data = event.get("data") or {}
                tool_call_id = str(data.get("tool_call_id") or "")
                tool_name = str(data.get("name") or "")
                tool_result = str(data.get("result") or "")
                if tool_call_id and tool_name:
                    session.add_message(
                        Message(
                            role="tool",
                            content=tool_result,
                            name=tool_name,
                            tool_call_id=tool_call_id,
                        )
                    )
            yield event

        # 流结束后保存助手回复
        final = event["data"].get("content", "") if event.get("type") == "done" else ""
        assistant_content = "".join(chunks) or str(final)
        if assistant_content:
            session.add_message(Message(role="assistant", content=assistant_content))
        await session_manager.save(session)
        await self._maybe_extract_memory(session, user_id)
        self.logger.info(
            f"Session {thread_id} updated with assistant message: {assistant_content[:20]}...",
            extra={"trace_id": get_trace_id()},
        )

    async def chat(
        self,
        query: str,
        user_id: str,
        thread_id: str,
    ) -> Dict[str, Any]:
        """非流式聊天：直接返回完整结果。"""
        content = ""
        async for event in self.chat_stream(query, user_id, thread_id):
            if event["type"] == "done":
                content = str(event["data"].get("content") or "")
        return {"type": "done", "data": {"content": content}}

    # ── 会话 CRUD ────────────────────────────────────────

    async def get_user_history_list(self, user_id: str) -> List[Dict[str, Any]]:
        session_manager = await self._get_session_manager()
        return await session_manager.list_by_user(user_id)

    async def delete_chat(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        session_manager = await self._get_session_manager()
        await session_manager.delete(thread_id, user_id=user_id)
        return {"status": "success", "thread_id": thread_id}

    async def get_thread_detail(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        session_manager = await self._get_session_manager()
        session = await session_manager.load(thread_id, user_id=user_id)
        if session is None:
            return {"thread_id": thread_id, "messages": [], "last_updated": None, "preview": None}

        items = [
            {"role": m.role, "content": m.content or "", "created_at": None}
            for m in session.messages
        ]
        return {
            "thread_id": session.session_id,
            "messages": items,
            "last_updated": session.updated_at.isoformat() if session.updated_at else None,
            "preview": session.preview,
        }

    # ── 私有方法 ──────────────────────────────────────────

    @staticmethod
    def _build_context(user_id: str, session_id: str) -> RequestContext:
        trace_id = get_trace_id() or uuid4().hex[:8]
        return RequestContext(user_id=user_id, session_id=session_id, trace_id=trace_id)

    async def _get_session_manager(self) -> SessionManager:
        if self._session_manager is None:
            self._session_manager = SessionManager(get_mongo_db())
        if not self._session_manager_ready:
            await self._session_manager.ensure_indexes()
            self._session_manager_ready = True
        return self._session_manager

    async def _maybe_extract_memory(self, session: Any, user_id: str) -> None:
        """触发后台记忆提取，避免阻塞主对话流。"""
        memory_runtime = getattr(self._agent, "memory_runtime", None)
        if memory_runtime is None:
            return
        turns = self._build_extraction_turns(session.get_recent_messages(max_messages=12))
        if not turns:
            return
        await send_task(
            TaskSubType.MEMORY_EXTRACTION,
            {"session_id": session.session_id, "user_id": user_id, "turns": turns},
            TaskPriority.NORMAL,
        )

    async def _ensure_initial_memory_context(self, session: Any, user_id: str) -> None:
        loop = getattr(self._agent, "_loop", None)
        if loop is None:
            return
        context_builder = getattr(loop, "context_builder", None)
        if context_builder is None:
            return
        if not context_builder._has_memory_access():
            return
        if session.metadata.get("agent_core_context") is None:
            agent_core = await context_builder._load_agent_core()
            if agent_core:
                session.metadata["agent_core_context"] = context_builder._format_memory_block("系统规则摘要", agent_core)
        if session.metadata.get("user_profile_context") is None:
            user_profile = await context_builder._load_user_profile(user_id)
            if user_profile:
                session.metadata["user_profile_context"] = context_builder._format_memory_block("用户画像摘要", user_profile)

    @staticmethod
    def _build_history_messages(session: Any) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        agent_core = session.metadata.get("agent_core_context")
        if agent_core:
            history.append({"role": "system", "content": agent_core, "section": "system_core"})
        user_profile = session.metadata.get("user_profile_context")
        if user_profile:
            history.append({"role": "system", "content": user_profile, "section": "memory_context"})
        history.extend([m.to_llm_dict() for m in session.messages])
        return history

    @staticmethod
    def _build_extraction_turns(messages: List[Message]) -> List[Dict[str, Any]]:
        """筛选可提取的用户/助手轮次，生成结构化输入。"""
        turns: List[Dict[str, Any]] = []
        for idx, msg in enumerate(messages, start=1):
            if msg.role not in {"user", "assistant"}:
                continue
            content = (msg.content or "").strip()
            if not content:
                continue
            turns.append({"role": msg.role, "content": content, "turn_id": str(idx)})
        return turns

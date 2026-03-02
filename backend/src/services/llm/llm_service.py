import os
from src.agent.lotus_agent import LotusDBAgent


class LLMService:
    def __init__(self):
        self._agent = None

    @property
    def agent(self) -> LotusDBAgent:
        if self._agent is None:
            self._agent = LotusDBAgent()
        return self._agent

    async def get_user_history_list(self, user_id: str):
        """获取用户历史记录"""
        threads_map = {}
        async for thread in self.agent.checkpointer.alist(
            None, filter={"user_id": user_id}
        ):
            thread_id = thread.config["configurable"]["thread_id"]
            if thread_id not in threads_map:
                threads_map[thread_id] = {
                    "thread_id": thread_id,
                    "last_updated": thread.metadata.get("updated_at"),
                    "preview": thread.metadata.get("query"),
                }
        return list(threads_map.values())

    async def chat(self, query: str, user_id: str, thread_id: str, Agent_version: str, stream: bool = False):
        """开始聊天"""
        if Agent_version not in self.agent.agent_versions:
            raise ValueError(f"Agent_version {Agent_version} is not supported. Supported versions are {self.agent.agent_versions}")
        if stream:
            async for event in self.agent.astream(query, user_id, thread_id):
                yield event
        else:
            response = await self.agent.ainvoke(query, user_id, thread_id)
            yield response

    async def delete_chat(self, user_id: str, thread_id: str):
        """删除用户聊天记录"""
        await self.agent.verify_ownership(thread_id, user_id)
        await self.agent.delete_chat(thread_id)
        return {"status": "success", "thread_id": thread_id}

    async def get_thread_detail(self, user_id: str, thread_id: str):
        await self.agent.verify_ownership(thread_id, user_id)
        config = {"configurable": {"thread_id": thread_id}}
        state = await self.agent.graph.aget_state(config)
        values = state.values or {}
        msgs = values.get("messages") or []
        items = []
        for m in msgs:
            try:
                role_type = getattr(m, "type", None) or ""
                role = "user" if role_type == "human" else "assistant" if role_type == "ai" else role_type or "system"
                content = getattr(m, "content", "")
                items.append({"role": role, "content": content})
            except Exception:
                pass
        return {
            "thread_id": thread_id,
            "messages": items,
            "last_updated": state.metadata.get("updated_at") if state and getattr(state, "metadata", None) else None,
            "preview": state.metadata.get("query") if state and getattr(state, "metadata", None) else None
        }

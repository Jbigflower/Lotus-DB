from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from .config import AgentConfig
from .llm.provider import LLMClient
from .tools.registry import ToolRegistry
from .memory.runtime import MemoryRuntime
from .types import AgentRole, RequestContext

if TYPE_CHECKING:
    from .loop import AgentLoop


class DelegationHandler:
    """管理子智能体的生成与执行。"""

    SPECIALIST_CONFIGS: Dict[str, AgentConfig] = {
        "media_search": AgentConfig(
            agent_id="sub_media_search",
            role=AgentRole.SPECIALIST,
            role_description=(
                "你是一位媒体搜索专家。你的专长是在媒体库和外部数据源中"
                "找到符合特定标准的电影、音乐和其他媒体内容。"
                "你搜索详尽，并始终解释每个结果为何相关。"
            ),
            goal="为给定标准找到最相关的媒体项目",
            constraints=[
                "返回结构化结果（标题、类型、年份、相关性理由）",
                "如果没有精确匹配，提供最接近的替代",
            ],
            allowed_tools=["search_media", "get_media_details", "query_database"],
            max_iterations=10,
            can_delegate=False,
            memory_access={
                "agent_memory": True,
                "user_memory": True,
                "session_memory": False,
            },
        ),
        "asset_management": AgentConfig(
            agent_id="sub_asset_mgmt",
            role=AgentRole.SPECIALIST,
            role_description="你是一位媒体库管理员，负责管理用户个人库。",
            goal="准确执行库管理操作并报告结果",
            constraints=["破坏性操作前确认", "操作完成后清晰报告变更内容"],
            allowed_tools=["add_to_library", "remove_from_library", "query_user_library"],
            max_iterations=8,
            can_delegate=False,
            memory_access={
                "agent_memory": True,
                "user_memory": True,
                "session_memory": False,
            },
        ),
        "external_research": AgentConfig(
            agent_id="sub_external_research",
            role=AgentRole.SPECIALIST,
            role_description="你是一位外部数据研究员，搜索网络和外部 API。",
            goal="找到准确、最新的外部信息",
            constraints=["引用信息来源", "标记不确定的信息"],
            allowed_tools=["web_search", "fetch_external_api"],
            max_iterations=10,
            can_delegate=False,
            memory_access={
                "agent_memory": True,
                "user_memory": True,
                "session_memory": False,
            },
        ),
    }

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_client: LLMClient,
        memory_runtime: Optional[MemoryRuntime] = None,
    ) -> None:
        """初始化委派处理器。

        Args:
            tool_registry: 工具注册表。
            llm_client: LLM 客户端。
            memory_runtime: 记忆运行时（用于子智能体共享）。
        """
        self._tools = tool_registry
        self._llm = llm_client
        self._memory_runtime = memory_runtime

    async def handle(
        self,
        task_description: str,
        context: str,
        expected_output: str,
        ctx: RequestContext,
        required_tools: Optional[List[str]] = None,
        specialist_type: str = "general",
    ) -> str:
        """生成子智能体并返回其结果摘要。"""
        config = self._build_config(task_description, required_tools, specialist_type)
        scoped_input = self._build_scoped_input(task_description, context, expected_output)
        result = await self._run_subagent(scoped_input, config, ctx)
        tools_used = ", ".join(result["tools"]) if result["tools"] else "[]"
        return (
            f"## 子智能体结果 (specialist: {specialist_type})\n"
            f"**状态:** {result['status']}\n"
            f"**迭代次数:** {result['iterations']}\n"
            f"**调用的工具:** {tools_used}\n\n"
            f"**输出:**\n{result['output']}"
        )

    def _build_config(
        self,
        task_description: str,
        required_tools: Optional[List[str]],
        specialist_type: str,
    ) -> AgentConfig:
        tools = [tool for tool in (required_tools or []) if tool != "delegate"]
        if specialist_type in self.SPECIALIST_CONFIGS:
            base = self.SPECIALIST_CONFIGS[specialist_type]
            config = replace(base)
            if tools:
                config.allowed_tools = tools
            return config
        return AgentConfig(
            agent_id=f"sub_{uuid4().hex[:8]}",
            role=AgentRole.DELEGATED,
            role_description="你是一个助手，正在处理一个特定的子任务。",
            goal=task_description,
            constraints=[],
            allowed_tools=tools,
            max_iterations=10,
            can_delegate=False,
            memory_access={
                "agent_memory": True,
                "user_memory": True,
                "session_memory": False,
            },
        )

    def _build_scoped_input(self, task_description: str, context: str, expected_output: str) -> str:
        return (
            "## 你的任务\n"
            f"{task_description}\n\n"
            "## 上下文\n"
            f"{context}\n\n"
            "## 期望输出\n"
            f"{expected_output}"
        )

    async def _run_subagent(
        self,
        user_input: str,
        config: AgentConfig,
        ctx: RequestContext,
    ) -> Dict[str, Any]:
        from .loop import AgentLoop

        loop = AgentLoop(
            llm=self._llm,
            tools=self._tools,
            config=config,
            memory_runtime=self._memory_runtime,
        )
        output = ""
        status = "ok"
        error_message = ""
        tool_calls: List[str] = []
        iterations = 0
        async for event in loop.run(user_input=user_input, ctx=ctx, history=None):
            event_type = event.get("type")
            data = event.get("data", {})
            if event_type == "text_delta":
                output += str(data.get("content") or "")
            elif event_type == "tool_start":
                name = data.get("name")
                if name:
                    tool_calls.append(name)
            elif event_type == "error":
                status = "error"
                error_message = str(data.get("message") or "")
            elif event_type == "done":
                iterations += 1
        if not output and error_message:
            output = f"子智能体执行失败: {error_message}"
        if not output:
            output = "子智能体未生成最终回复。"
        return {
            "output": output,
            "status": status,
            "iterations": iterations or 1,
            "tools": tool_calls,
            "error_message": error_message or None,
        }

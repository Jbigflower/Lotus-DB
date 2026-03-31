from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from config.logging import get_logic_logger
from config.setting import get_settings

from .config import AgentConfig
from .llm.provider import LLMClient
from .loop import AgentLoop
from .memory.runtime import MemoryRuntime
from .tools.registry import ToolRegistry
from .types import AgentRole, RequestContext, StreamEvent

# For LLM client configuration
try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


class LotusAgent:
    """无状态推理引擎：接收输入 + 历史，产出流式事件。"""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
        config: Optional[AgentConfig] = None,
        memory_runtime: Optional[MemoryRuntime] = None,
    ) -> None:
        self.logger = get_logic_logger("lotus_agent")
        self._settings = get_settings()
        self._tools = tool_registry or self._build_registry()
        self._llm = llm_client or self._build_llm()
        self._config = config or self._build_config(self._tools)
        self._memory_runtime = memory_runtime or MemoryRuntime(self._llm)
        self._loop = AgentLoop(
            llm=self._llm,
            tools=self._tools,
            config=self._config,
            memory_runtime=self._memory_runtime,
        )

    async def run(
        self,
        query: str,
        history: List[dict],
        ctx: RequestContext,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        核心推理入口。
        输入：用户查询 + 历史消息 + 请求上下文
        输出：流式事件（text_delta / tool_call / done）
        """
        async for event in self._loop.run(
            user_input=query, ctx=ctx, history=history
        ):
            yield event

    @property
    def memory_runtime(self) -> MemoryRuntime:
        """暴露记忆运行时供 Service 层触发抽取流程。"""
        return self._memory_runtime

    # ── 内部构建方法 ──────────────────────────────────────

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        _TOOL_MODULES = [
            ("src.agent.tools.movie_tools", "register_movie_tools"),
            ("src.agent.tools.library_tools", "register_library_tools"),
            ("src.agent.tools.collection_tools", "register_collection_tools"),
            ("src.agent.tools.asset_tools", "register_asset_tools"),
            ("src.agent.tools.user_asset_tools", "register_user_asset_tools"),
            ("src.agent.tools.watch_history_tools", "register_watch_history_tools"),
            ("src.agent.tools.search_tools", "register_search_tools"),
            ("src.agent.tools.task_tools", "register_task_tools"),
        ]
        for module_path, fn_name in _TOOL_MODULES:
            try:
                module = __import__(module_path, fromlist=[fn_name])
                getattr(module, fn_name)(registry)
            except Exception as exc:
                self.logger.warning(f"tool_registry_skip:{module_path}:{fn_name}:{exc}")
        return registry

    def _build_llm(self) -> LLMClient:
        s = self._settings.llm
        
        # Check if OpenAI client is available
        if AsyncOpenAI is None:
            self.logger.warning("OpenAI client not available. LLM will not be functional.")
            return LLMClient(completion_fn=None)
        
        # Create OpenAI client
        client = AsyncOpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_base_url)
        
        # Create completion function
        async def completion_fn(**kwargs: Any):
            kwargs.pop("api_key", None)
            kwargs.pop("api_base", None)
            return await client.chat.completions.create(**kwargs)

        async def stream_fn(**kwargs: Any):
            kwargs.pop("api_key", None)
            kwargs.pop("api_base", None)
            kwargs["stream"] = True
            stream = await client.chat.completions.create(**kwargs)
            async for chunk in stream:
                yield chunk
        
        return LLMClient(
            api_key=s.deepseek_api_key,
            api_base=s.deepseek_base_url,
            default_model=s.deepseek_model,
            completion_fn=completion_fn,
            stream_fn=stream_fn,
        )

    def _build_config(self, tools: ToolRegistry) -> AgentConfig:
        return AgentConfig(
            agent_id="lotus_v2_main",
            role=AgentRole.MAIN,
            role_description="你是 Lotus-DB 的智能助理，擅长检索与管理媒体信息。",
            goal="为用户提供准确的媒体检索与管理协助。",
            constraints=["高风险操作前进行确认", "优先使用工具完成查询与写入"],
            allowed_tools=tools.tool_names,
            max_iterations=25,
            can_delegate=True,
            memory_access={
                "agent_memory": True,
                "user_memory": True,
                "session_memory": True,
            },
        )

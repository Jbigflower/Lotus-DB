from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from .base import ToolDefinition
from ..types import RequestContext, ToolResult
from config.logging import get_repo_logger

class ToolRegistry:
    """工具注册表，用于动态注册与执行工具。
    LLM 返回 tool_call
    → Agent Loop 调用 registry.execute(name, params, ctx)
        → cast_params (类型转换)
        → validate_params (校验)
        → _handler_accepts_ctx (判断是否注入 ctx)
        → tool.execute(**exec_params)
    → 结果返回给 Agent Loop
    """

    def __init__(self) -> None:
        """初始化工具注册表。"""
        self._tools: Dict[str, ToolDefinition] = {}
        self.logger = get_repo_logger("ToolRegistry")

    def register(self, tool: ToolDefinition) -> None:
        """注册工具。

        Args:
            tool: 工具定义。
        """
        if self.has(name := tool.name):
            self.logger.warning(f"Tool name '{name}' is already registered.")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销工具。

        Args:
            name: 工具名称。
        """
        if not self.has(name):
            self.logger.warning(f"Tool name '{name}' is not registered.")
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """按名称获取工具。

        Args:
            name: 工具名称。

        Returns:
            工具定义或 None。
        """
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """判断工具是否已注册。

        Args:
            name: 工具名称。

        Returns:
            是否存在。
        """
        return name in self._tools

    def get_tools(self, allowed: Optional[List[str]] = None) -> Dict[str, ToolDefinition]:
        """根据白名单获取工具集合。

        Args:
            allowed: 允许的工具名称列表。

        Returns:
            工具字典。
        """
        if not allowed:
            return dict(self._tools)
        return {n: t for n, t in self._tools.items() if n in allowed}

    def get_tool_schemas(self, allowed: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """获取 OpenAI 兼容的工具 schema 列表。

        Args:
            allowed: 允许的工具名称列表。

        Returns:
            OpenAI tools schema 数组。
        """
        return [tool.to_schema() for tool in self.get_tools(allowed).values()]

    async def execute(
        self,
        name: str,
        params: Dict[str, Any],
        ctx: Optional[RequestContext] = None,
    ) -> ToolResult:
        """执行工具。

        Args:
            name: 工具名称。
            params: 工具参数。
            ctx: 请求上下文。

        Returns:
            工具执行结果。
        """
        hint = "\n\n[Analyze the error above and try a different approach.]"
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                output=f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}",
                error="tool_not_found",
            )

        try:
            params = tool.cast_params(params)
            errors = tool.validate_params(params)
            if errors:
                return ToolResult(
                    output=f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors) + hint,
                    error="invalid_params",
                )
            exec_params = dict(params)
            if ctx is not None and self._handler_accepts_ctx(tool):
                exec_params["ctx"] = ctx
            result = await tool.execute(**exec_params)
            if result.is_error:
                return ToolResult(output=result.output + hint, error=result.error)
            return result
        except Exception as e:
            return ToolResult(
                output=f"Error executing {name}: {str(e)}" + hint,
                error="tool_exception",
            )

    def _handler_accepts_ctx(self, tool: ToolDefinition) -> bool:
        """判断处理函数是否接受 ctx 参数。

        Args:
            tool: 工具定义。

        Returns:
            是否接受 ctx。
        """
        try:
            signature = inspect.signature(tool.handler)
        except (TypeError, ValueError):
            return False
        for param in signature.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True
        return "ctx" in signature.parameters

    @property
    def tool_names(self) -> List[str]:
        """获取已注册工具名称列表。

        Returns:
            工具名称列表。
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        """返回工具数量。"""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """判断工具名称是否存在。"""
        return name in self._tools

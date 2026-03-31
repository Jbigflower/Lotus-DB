import pytest
from typing import Any, Dict

from src.agent.tools.base import ToolDefinition
from src.agent.tools.registry import ToolRegistry
from src.agent.types import RequestContext


async def fake_search_handler(q: str, ctx: RequestContext) -> str:
    """用于测试的搜索工具处理函数。"""
    return f"{q}:{ctx.user_id}"


async def fake_list_handler(page: int, size: int, query: str) -> str:
    return f"{page}:{size}:{query}"


def build_tool() -> ToolDefinition:
    """构造测试用工具定义。"""
    return ToolDefinition(
        name="search_media",
        description="搜索媒体。",
        parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
        handler=fake_search_handler,
        category="media_search",
    )


def build_list_tool() -> ToolDefinition:
    return ToolDefinition(
        name="list_items",
        description="列出项目。",
        parameters={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "default": 1},
                "size": {"type": "integer", "default": 20},
                "query": {"type": "string", "default": None},
            },
        },
        handler=fake_list_handler,
        category="list",
    )


def test_get_tool_schemas_openai_format() -> None:
    """验证工具 schema 输出符合 OpenAI 规范。"""
    registry = ToolRegistry()
    tool = build_tool()
    registry.register(tool)

    schemas = registry.get_tool_schemas()

    assert schemas == [
        {
            "type": "function",
            "function": {
                "name": "search_media",
                "description": "搜索媒体。",
                "parameters": tool.parameters,
            },
        }
    ]


@pytest.mark.asyncio
async def test_execute_tool_with_ctx() -> None:
    """验证工具执行能传递 ctx 并返回结果。"""
    registry = ToolRegistry()
    registry.register(build_tool())
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    result = await registry.execute("search_media", {"q": "hello"}, ctx=ctx)

    assert result.output == "hello:u1"
    assert result.error is None


@pytest.mark.asyncio
async def test_execute_tool_applies_defaults() -> None:
    registry = ToolRegistry()
    registry.register(build_list_tool())

    result = await registry.execute("list_items", {"page": 2})

    assert result.output == "2:20:None"
    assert result.error is None

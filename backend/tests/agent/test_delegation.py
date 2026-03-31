from typing import Any, Dict, List

import pytest

from src.agent.delegation import DelegationHandler
from src.agent.llm.provider import LLMClient
from src.agent.tools.registry import ToolRegistry
from src.agent.types import RequestContext


class FakeCompletion:
    def __init__(self, content: str) -> None:
        self._content = content

    async def __call__(self, **_: Any) -> Dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {"content": self._content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


@pytest.mark.asyncio
async def test_delegation_handler_runs_subagent() -> None:
    llm = LLMClient(completion_fn=FakeCompletion("完成"))
    tools = ToolRegistry()
    handler = DelegationHandler(tool_registry=tools, llm_client=llm)
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    result = await handler.handle(
        task_description="查找音乐",
        context="用户偏好爵士乐",
        expected_output="返回列表",
        ctx=ctx,
        required_tools=["search_media", "delegate"],
        specialist_type="general",
    )

    assert "子智能体结果" in result
    assert "完成" in result


def test_delegation_specialist_config_overrides_tools() -> None:
    llm = LLMClient(completion_fn=FakeCompletion("ok"))
    tools = ToolRegistry()
    handler = DelegationHandler(tool_registry=tools, llm_client=llm)

    config = handler._build_config(
        task_description="测试任务",
        required_tools=["search_media", "delegate"],
        specialist_type="media_search",
    )

    assert "delegate" not in config.allowed_tools
    assert config.can_delegate is False
    assert config.memory_access["session_memory"] is False

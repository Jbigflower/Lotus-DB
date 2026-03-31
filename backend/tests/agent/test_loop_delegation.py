import pytest
from typing import Any, Dict, List

from src.agent.config import AgentConfig
from src.agent.llm.provider import LLMClient
from src.agent.loop import AgentLoop
from src.agent.tools.registry import ToolRegistry
from src.agent.types import AgentRole, RequestContext


class FakeLLM:
    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete(self, **kwargs: Any) -> Dict[str, Any]:
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


class FakeDelegationHandler:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def handle(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return "delegated-result"


class PassthroughAssembler:
    async def fit_to_budget(self, messages: List[Dict[str, Any]], _: AgentConfig) -> List[Dict[str, Any]]:
        return messages


def build_config() -> AgentConfig:
    return AgentConfig(
        agent_id="agent-1",
        role=AgentRole.MAIN,
        role_description="测试助手",
        goal="回答问题",
        constraints=[],
        allowed_tools=["delegate"],
        max_iterations=5,
        can_delegate=True,
    )


@pytest.mark.asyncio
async def test_loop_delegate_triggers_handler() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "delegate",
                                    "arguments": "{\"task_description\":\"研究X\",\"context\":\"背景\",\"expected_output\":\"要点\"}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]},
    ]
    llm = LLMClient(completion_fn=FakeLLM(responses).complete)
    tools = ToolRegistry()
    delegation = FakeDelegationHandler()
    loop = AgentLoop(
        llm=llm,
        tools=tools,
        config=build_config(),
        context_assembler=PassthroughAssembler(),
        delegation_handler=delegation,
    )
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    events = []
    async for event in loop.run("帮我研究X", ctx):
        events.append(event)

    types = [e["type"] for e in events]
    assert "tool_start" in types
    assert "tool_end" in types
    assert types[-1] == "done"
    assert delegation.calls

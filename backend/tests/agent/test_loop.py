import pytest
from typing import Any, Dict, List

from src.agent.config import AgentConfig
from src.agent.llm.provider import LLMClient
from src.agent.loop import AgentLoop
from src.agent.tools.base import ToolDefinition
from src.agent.tools.registry import ToolRegistry
from src.agent.types import AgentRole, RequestContext
from src.agent.memory.models import MemoryCategory, MemoryItem, MemoryTier
from src.agent.memory.retriever import AssembledMemory


class FakeLLM:
    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete(self, **kwargs: Any) -> Dict[str, Any]:
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def retrieve_for_context(self, **kwargs: Any) -> AssembledMemory:
        self.calls.append(kwargs)
        return AssembledMemory(
            session=[
                MemoryItem(
                    tier=MemoryTier.SESSION,
                    session_id=kwargs.get("session_id"),
                    category=MemoryCategory.BEHAVIOR,
                    content="会话偏好",
                )
            ],
            user=[
                MemoryItem(
                    tier=MemoryTier.USER,
                    user_id=kwargs.get("user_id"),
                    category=MemoryCategory.PREFERENCE,
                    content="喜欢科幻",
                )
            ],
            agent=[
                MemoryItem(
                    tier=MemoryTier.AGENT,
                    category=MemoryCategory.KNOWLEDGE,
                    content="检索时优先最新数据",
                )
            ],
        )


class FakeMemoryRuntime:
    def __init__(self, retriever: FakeRetriever) -> None:
        self.retriever = retriever
        self.agent_calls = 0
        self.user_calls = 0

    async def get_agent_core_memories(self, limit: int = 10) -> List[MemoryItem]:
        self.agent_calls += 1
        return [
            MemoryItem(
                tier=MemoryTier.AGENT,
                category=MemoryCategory.KNOWLEDGE,
                content="遵循系统流程",
            )
        ]

    async def get_user_profile_memories(self, user_id: str, limit: int = 10) -> List[MemoryItem]:
        self.user_calls += 1
        return [
            MemoryItem(
                tier=MemoryTier.USER,
                user_id=user_id,
                category=MemoryCategory.PREFERENCE,
                content="偏好纪录片",
            )
        ]

    async def get_retriever(self) -> FakeRetriever:
        return self.retriever


def build_config() -> AgentConfig:
    return AgentConfig(
        agent_id="agent-1",
        role=AgentRole.MAIN,
        role_description="测试助手",
        goal="回答问题",
        constraints=[],
        allowed_tools=["echo"],
        max_iterations=5,
        can_delegate=False,
    )


@pytest.mark.asyncio
async def test_loop_no_tools_emits_text_and_done() -> None:
    responses = [
        {
            "choices": [
                {"message": {"content": "hello"}, "finish_reason": "stop"},
            ]
        }
    ]
    llm = LLMClient(completion_fn=FakeLLM(responses).complete)
    tools = ToolRegistry()
    loop = AgentLoop(llm=llm, tools=tools, config=build_config())
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    events = []
    async for event in loop.run("hi", ctx):
        events.append(event)

    assert events[0]["type"] == "text_delta"
    assert events[0]["data"]["content"] == "hello"
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_loop_with_tool_emits_tool_events() -> None:
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
                                "function": {"name": "echo", "arguments": "{\"text\": \"hi\"}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {
            "choices": [
                {"message": {"content": "done"}, "finish_reason": "stop"},
            ]
        },
    ]
    llm = LLMClient(completion_fn=FakeLLM(responses).complete)
    tools = ToolRegistry()

    async def echo(text: str, ctx: RequestContext) -> str:
        return f"{text}:{ctx.user_id}"

    tools.register(
        ToolDefinition(
            name="echo",
            description="echo",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=echo,
            category="test",
        )
    )

    loop = AgentLoop(llm=llm, tools=tools, config=build_config())
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    events = []
    async for event in loop.run("hi", ctx):
        events.append(event)

    types = [e["type"] for e in events]
    assert types[0] == "tool_start"
    assert types[1] == "tool_end"
    assert types[-2] == "text_delta"
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_loop_build_messages_initial_memory_injection() -> None:
    llm = LLMClient(completion_fn=FakeLLM([{"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}]).complete)
    retriever = FakeRetriever()
    runtime = FakeMemoryRuntime(retriever)
    loop = AgentLoop(llm=llm, tools=ToolRegistry(), config=build_config(), memory_runtime=runtime)
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    messages = await loop.context_builder.build_messages("hi", history=None, ctx=ctx)
    contents = [m.get("content", "") for m in messages if m.get("role") == "system"]

    assert any("系统规则摘要" in c for c in contents)
    assert any("用户画像摘要" in c for c in contents)
    assert any("相关知识" in c for c in contents)
    assert runtime.agent_calls == 1
    assert runtime.user_calls == 1
    assert retriever.calls


@pytest.mark.asyncio
async def test_loop_build_messages_skips_duplicate_initial_memory() -> None:
    llm = LLMClient(completion_fn=FakeLLM([{"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}]).complete)
    retriever = FakeRetriever()
    runtime = FakeMemoryRuntime(retriever)
    loop = AgentLoop(llm=llm, tools=ToolRegistry(), config=build_config(), memory_runtime=runtime)
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")
    history = [
        {"role": "system", "content": "系统规则摘要\n- 遵循系统流程"},
        {"role": "system", "content": "用户画像摘要\n- 偏好纪录片"},
        {"role": "user", "content": "hello"},
    ]

    messages = await loop.context_builder.build_messages("hi", history=history, ctx=ctx)
    contents = [m.get("content", "") for m in messages if m.get("role") == "system"]

    assert sum(1 for c in contents if c.startswith("系统规则摘要")) == 1
    assert sum(1 for c in contents if c.startswith("用户画像摘要")) == 1
    assert runtime.agent_calls == 0
    assert runtime.user_calls == 0
    assert retriever.calls

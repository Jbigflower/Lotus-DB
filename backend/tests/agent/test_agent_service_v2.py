import pytest
from mongomock_motor import AsyncMongoMockClient

from src.agent.config import AgentConfig
from src.agent.llm.provider import LLMClient
from src.agent.tools.registry import ToolRegistry
from src.agent.types import AgentRole
from src.agent.session import SessionManager
from src.agent.lotus_agent import LotusAgent


async def fake_completion(**kwargs):
    return {
        "choices": [
            {
                "message": {"content": "你好"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


@pytest.mark.asyncio
async def test_lotus_agent_stream_chat_persists_session() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    session_manager = SessionManager(collection)
    llm_client = LLMClient(completion_fn=fake_completion)
    registry = ToolRegistry()
    config = AgentConfig(
        agent_id="test_agent",
        role=AgentRole.MAIN,
        role_description="测试助手",
        goal="测试对话",
        constraints=[],
        allowed_tools=[],
        max_iterations=5,
        can_delegate=False,
    )
    agent = LotusAgent(
        llm_client=llm_client,
        tool_registry=registry,
        session_manager=session_manager,
        config=config,
        session_collection=collection,
    )

    events = []
    async for event in agent.chat("你好", "u1", "t1", stream=True):
        events.append(event)

    assert any(e["type"] == "text_delta" for e in events)
    loaded = await session_manager.load("t1", "u1")
    assert loaded is not None
    assert loaded.messages[0].role == "user"
    assert loaded.messages[1].role == "assistant"
    assert loaded.messages[1].content == "你好"


@pytest.mark.asyncio
async def test_lotus_agent_non_stream_returns_done() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    session_manager = SessionManager(collection)
    llm_client = LLMClient(completion_fn=fake_completion)
    registry = ToolRegistry()
    config = AgentConfig(
        agent_id="test_agent",
        role=AgentRole.MAIN,
        role_description="测试助手",
        goal="测试对话",
        constraints=[],
        allowed_tools=[],
        max_iterations=5,
        can_delegate=False,
    )
    agent = LotusAgent(
        llm_client=llm_client,
        tool_registry=registry,
        session_manager=session_manager,
        config=config,
        session_collection=collection,
    )

    events = []
    async for event in agent.chat("你好", "u1", "t2", stream=False):
        events.append(event)

    assert len(events) == 1
    assert events[0]["type"] == "done"
    assert events[0]["data"]["content"] == "你好"

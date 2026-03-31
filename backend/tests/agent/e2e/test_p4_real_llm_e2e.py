import os
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from openai import AsyncOpenAI
from dotenv import load_dotenv

from src.agent.config import AgentConfig
from src.agent.llm.provider import LLMClient
from src.agent.session import SessionManager
from src.agent.tools.base import ToolDefinition
from src.agent.tools.registry import ToolRegistry
from src.agent.types import AgentRole, Message, RequestContext
from src.agent.lotus_agent import LotusAgent
from src.services.llm.llm_service import LLMService
from src.routers.llm import router as llm_router
import src.routers.llm as llm_mod
from src.core.dependencies import get_current_user


class FakeUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id
        self.username = "real-llm-tester"

load_dotenv()


def _build_real_llm() -> LLMClient:
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com"
    if not api_key:
        pytest.skip("Skipping real LLM test: DEEPSEEK_API_KEY not found")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        api_key=api_key,
        api_base=base_url,
        default_model="deepseek-chat",
        completion_fn=completion_fn,
        stream_fn=stream_fn,
    )


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    async def search_media(q: str, ctx: RequestContext) -> str:
        return f"搜索结果:{q}"

    registry.register(
        ToolDefinition(
            name="search_media",
            description="搜索媒体",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            handler=search_media,
            category="search",
        )
    )
    return registry


def _build_service(
    collection,
    allowed_tools: List[str] | None = None,
    constraints: List[str] | None = None,
    role_description: str | None = None,
) -> LLMService:
    llm_client = _build_real_llm()
    registry = _build_registry()
    allowed = allowed_tools or ["search_media", "delegate"]
    config = AgentConfig(
        agent_id="p4-real-llm",
        role=AgentRole.MAIN,
        role_description=role_description or "你是 Lotus-DB 的智能助理，必须按指令调用工具。",
        goal="执行端到端验收场景。",
        constraints=constraints or ["当用户要求调用工具时必须调用工具"],
        allowed_tools=allowed,
        max_iterations=8,
        can_delegate=True,
    )
    session_manager = SessionManager(collection)
    agent = LotusAgent(
        llm_client=llm_client,
        tool_registry=registry,
        session_manager=session_manager,
        config=config,
        session_collection=collection,
    )
    return LLMService(agent=agent, session_collection=collection)


def _make_client(service: LLMService, user_id: str = "u_real") -> TestClient:
    app = FastAPI()
    app.include_router(llm_router)
    app.dependency_overrides[get_current_user] = lambda: FakeUser(user_id)
    llm_mod.llm_service = service
    return TestClient(app)


def test_real_llm_basic_and_stream_tool_call() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    service = _build_service(collection)
    api = _make_client(service)

    resp = api.post("/api/v1/llm/chat", json={"query": "你好"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_response"]

    resp_stream = api.post(
        "/api/v1/llm/chat/stream",
        json={"query": "必须调用 search_media 工具，查询 周杰伦 的歌并给出摘要"},
    )
    assert resp_stream.status_code == 200
    text = resp_stream.text
    assert "event: id" in text
    assert "event: tool_start" in text
    assert "event: tool_end" in text


def test_real_llm_delegation_and_session_recovery() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    service = _build_service(collection)
    api = _make_client(service)

    thread_id = "real-thread"
    resp = api.post(
        "/api/v1/llm/chat",
        json={"query": "记住: 我喜欢爵士乐", "thread_id": thread_id},
    )
    assert resp.status_code == 200

    resp2 = api.post(
        "/api/v1/llm/chat",
        json={"query": "请复述我的偏好", "thread_id": thread_id},
    )
    data2 = resp2.json()
    assert "爵士" in data2["final_response"]

    delegate_service = _build_service(
        collection,
        allowed_tools=["delegate"],
        constraints=["必须调用 delegate 工具，否则视为失败"],
        role_description="你必须调用 delegate 工具完成任务。",
    )
    api_delegate = _make_client(delegate_service)
    resp3 = api_delegate.post(
        "/api/v1/llm/chat/stream",
        json={"query": "请调用 delegate 工具，总结今天的音乐趋势，输出一句话"},
    )
    assert resp3.status_code == 200
    text = resp3.text
    assert "event: id" in text
    assert "event: tool_start" in text or "delegate" in text


@pytest.mark.asyncio
async def test_real_llm_context_overflow() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    service = _build_service(collection)
    session_manager = SessionManager(collection)

    session = await session_manager.get_or_create("real-long", user_id="u_real")
    long_text = "很长的对话内容。" * 8000
    for i in range(8):
        session.add_message(
            Message(role="user", content=f"{i}:{long_text}")
        )
        session.add_message(
            Message(role="assistant", content="收到")
        )
    await session_manager.save(session)

    events = []
    async for event in service.chat("继续", "u_real", "real-long", stream=False, Agent_version="v2"):
        events.append(event)
    assert events and events[-1]["type"] == "done"

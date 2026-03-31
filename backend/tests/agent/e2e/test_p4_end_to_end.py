import json
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from src.agent.config import AgentConfig
from src.agent.llm.provider import LLMClient
from src.agent.session import SessionManager
from src.agent.tools.base import ToolDefinition
from src.agent.tools.registry import ToolRegistry
from src.agent.types import AgentRole, Message, RequestContext
from src.services.llm.agent_service_v2 import AgentServiceV2
from src.services.llm.llm_service import LLMService
from src.routers.llm import router as llm_router
import src.routers.llm as llm_mod
from src.core.dependencies import get_current_user


class FakeUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id
        self.username = "tester"


class FakeLLM:
    """用于端到端测试的 LLM 假实现。"""

    def __init__(self) -> None:
        self.prompts: List[str] = []

    async def complete(self, **kwargs: Any) -> Dict[str, Any]:
        messages = kwargs.get("messages") or []
        last = messages[-1] if messages else {}
        content = last.get("content") if isinstance(last, dict) else ""
        content = content or ""
        if "将以下对话精炼为简洁摘要" in content or "摘要对话" in content or "现有摘要" in content:
            self.prompts.append(content)
            return _text_response("summary-ok")
        for msg in reversed(messages):
            if msg.get("role") == "tool":
                return _text_response(f"已完成: {msg.get('content')}")
        if "搜索周杰伦" in content:
            return _tool_response(
                name="search_media",
                arguments={"q": "周杰伦"},
            )
        if "帮我深入研究" in content:
            return _tool_response(
                name="delegate",
                arguments={
                    "task_description": "研究X",
                    "context": "用户需要研究主题X",
                    "expected_output": "总结要点",
                    "specialist_type": "general",
                    "required_tools": [],
                },
            )
        if "推荐一些音乐" in content:
            if any("我喜欢爵士乐" in (m.get("content") or "") for m in messages):
                return _text_response("根据你喜欢爵士乐，推荐爵士经典专辑。")
        return _text_response("你好")


def _tool_response(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
    }


def _text_response(content: str) -> Dict[str, Any]:
    return {
        "choices": [
            {
                "message": {"content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }


def _build_service(fake_llm: FakeLLM, collection) -> LLMService:
    registry = ToolRegistry()

    async def fake_search_handler(q: str, ctx: RequestContext) -> str:
        return f"搜索结果:{q}"

    registry.register(
        ToolDefinition(
            name="search_media",
            description="搜索媒体",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            handler=fake_search_handler,
            category="search",
        )
    )
    llm_client = LLMClient(completion_fn=fake_llm.complete)
    config = AgentConfig(
        agent_id="p4-e2e",
        role=AgentRole.MAIN,
        role_description="测试助手",
        goal="完成端到端验证",
        constraints=[],
        allowed_tools=["search_media", "delegate"],
        max_iterations=6,
        can_delegate=True,
    )
    session_manager = SessionManager(collection)
    agent_service = AgentServiceV2(
        llm_client=llm_client,
        tool_registry=registry,
        session_manager=session_manager,
        config=config,
        session_collection=collection,
    )
    return LLMService(agent_service=agent_service, session_collection=collection)


def _make_client(service: LLMService, user_id: str = "u1") -> TestClient:
    app = FastAPI()
    app.include_router(llm_router)
    app.dependency_overrides[get_current_user] = lambda: FakeUser(user_id)
    llm_mod.llm_service = service
    return TestClient(app)


def test_p4_stream_tool_call_and_delegation() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    fake_llm = FakeLLM()
    service = _build_service(fake_llm, collection)
    api = _make_client(service)

    resp = api.post("/api/v1/llm/chat/stream", json={"query": "搜索周杰伦的歌"})
    assert resp.status_code == 200
    text = resp.text
    assert "event: id" in text
    assert "event: tool_start" in text
    assert "event: tool_end" in text
    assert "event: text_delta" in text

    resp2 = api.post("/api/v1/llm/chat", json={"query": "帮我深入研究X"})
    data = resp2.json()
    assert "子智能体结果" in data["final_response"]


def test_p4_session_recovery_and_preference() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    fake_llm = FakeLLM()
    service = _build_service(fake_llm, collection)
    api = _make_client(service)

    thread_id = "t-pref"
    resp = api.post("/api/v1/llm/chat", json={"query": "我喜欢爵士乐", "thread_id": thread_id})
    assert resp.status_code == 200

    service2 = _build_service(fake_llm, collection)
    api2 = _make_client(service2)
    resp2 = api2.post("/api/v1/llm/chat", json={"query": "推荐一些音乐", "thread_id": thread_id})
    data = resp2.json()
    assert "爵士乐" in data["final_response"]


@pytest.mark.asyncio
async def test_p4_context_overflow_triggers_summary() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["agent_sessions"]
    fake_llm = FakeLLM()
    service = _build_service(fake_llm, collection)

    session_manager = SessionManager(collection)
    session = await session_manager.get_or_create("t-long", user_id="u1")
    long_text = "长文本" * 20000
    for i in range(8):
        session.add_message(Message(role="user", content=f"{i}-{long_text}"))
        session.add_message(Message(role="assistant", content=f"{i}-ok"))
    await session_manager.save(session)

    events = []
    async for event in service.chat("继续", "u1", "t-long", stream=False, Agent_version="v2"):
        events.append(event)
    assert fake_llm.prompts

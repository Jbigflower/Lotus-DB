import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.llm import router as llm_router
import src.routers.llm as llm_mod
from src.core.dependencies import get_current_user
from src.models import UserRead, UserRole


class FakeService:
    async def chat(self, query: str, user_id: str, thread_id: str):
        return {"type": "done", "data": {"content": "hi"}}

    async def chat_stream(self, query: str, user_id: str, thread_id: str):
        yield {"type": "text_delta", "data": {"content": "hi"}}
        yield {"type": "done", "data": {"content": "hi"}}


def make_user() -> UserRead:
    return UserRead(
        id="u1",
        username="tester",
        email="t@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        is_deleted=False,
    )


def make_app(fake_user: UserRead | None = None, fake_service: FakeService | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(llm_router)
    app.dependency_overrides[get_current_user] = lambda: fake_user or make_user()
    llm_mod.llm_service = fake_service or FakeService()
    return TestClient(app)


def test_chat_returns_final_response() -> None:
    client = make_app()
    resp = client.post("/api/v1/llm/chat", json={"query": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_response"] == "hi"
    assert data["thread_id"]


def test_chat_stream_emits_sse_events() -> None:
    client = make_app()
    resp = client.post("/api/v1/llm/chat/stream", json={"query": "hello"})
    assert resp.status_code == 200
    text = resp.text
    assert "event: id" in text
    assert "event: text_delta" in text

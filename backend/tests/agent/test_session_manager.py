import pytest
from mongomock_motor import AsyncMongoMockClient

from src.agent.session import Session, SessionManager
from src.agent.types import Message


@pytest.mark.asyncio
async def test_session_manager_roundtrip() -> None:
    client = AsyncMongoMockClient()
    db = client["test_db"]
    manager = SessionManager(db)

    session = Session(session_id="s1", user_id="u1")
    session.add_message(Message(role="user", content="你好"))
    session.add_message(Message(role="assistant", content="已收到"))
    await manager.save(session)

    loaded = await manager.load("s1", "u1")
    assert loaded is not None
    assert loaded.session_id == "s1"
    assert loaded.user_id == "u1"
    assert [m.role for m in loaded.messages] == ["user", "assistant"]
    assert loaded.messages[1].content == "已收到"

    history = loaded.to_history()
    llm_messages = history.to_llm_messages()
    assert llm_messages[-1]["content"] == "已收到"


def test_session_history_alignment() -> None:
    session = Session(session_id="s2", user_id="u2")
    session.add_message(Message(role="assistant", content="工具调用结果"))
    session.add_message(Message(role="tool", content="结果", name="search_media", tool_call_id="t1"))
    session.add_message(Message(role="user", content="继续"))
    session.add_message(Message(role="assistant", content="好的"))
    recent_messages = session.get_recent_messages(max_messages=10)
    assert recent_messages[0].role == "user"
    assert recent_messages[0].content == "继续"

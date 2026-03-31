import json
from typing import Dict
from src.agent.config import AgentConfig
from src.agent.types import AgentRole, ConversationHistory, Message, ToolCall, ToolFunctionCall


def test_agent_config_fields() -> None:
    """验证 AgentConfig 字段完整且默认值正确。"""

    config = AgentConfig(
        agent_id="agent_main",
        role=AgentRole.MAIN,
        role_description="你是媒体搜索专家",
        goal="帮助用户找到内容",
        constraints=["保持简洁"],
        allowed_tools=["search_media"],
    )

    assert config.agent_id == "agent_main"
    assert config.role == AgentRole.MAIN
    assert config.role_description == "你是媒体搜索专家"
    assert config.goal == "帮助用户找到内容"
    assert config.constraints == ["保持简洁"]
    assert config.allowed_tools == ["search_media"]
    assert config.max_iterations == 25
    assert config.can_delegate is True
    assert config.initial_context == []
    assert config.memory_access == {
        "agent_memory": True,
        "user_memory": True,
        "session_memory": True,
    }


def test_conversation_history_basic() -> None:
    """验证 ConversationHistory 的基础行为。"""

    history = ConversationHistory()
    history.add(Message(role="user", content="你好"))
    history.add(Message(role="assistant", content="你好，有什么可以帮你？"))

    recent = history.get_recent(1)
    assert len(recent) == 1
    assert recent[0].content == "你好，有什么可以帮你？"

    llm_messages = history.to_llm_messages()
    assert llm_messages[0]["role"] == "user"
    assert llm_messages[0]["content"] == "你好"


def test_message_tool_call_conversion() -> None:
    """验证工具调用消息转换为 LLM 结构。"""

    tool_call = ToolCall(
        id="call_1",
        function=ToolFunctionCall(name="search_media", arguments={"q": "周杰伦"}),
    )
    message = Message(role="assistant", content=None, tool_calls=[tool_call])
    llm_message: Dict[str, object] = message.to_llm_dict()

    assert llm_message["role"] == "assistant"
    assert "tool_calls" in llm_message
    tool_calls = llm_message["tool_calls"]
    assert isinstance(tool_calls, list)
    assert tool_calls[0]["function"]["name"] == "search_media"


def test_stream_event_json_serializable() -> None:
    """验证 StreamEvent 可 JSON 序列化。"""

    event = {"type": "text_delta", "data": {"content": "hi"}}
    payload = json.dumps(event, ensure_ascii=False)
    assert "text_delta" in payload

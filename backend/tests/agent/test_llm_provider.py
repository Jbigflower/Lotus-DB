import pytest
from typing import Any, Dict, List

from src.agent.llm.provider import LLMClient, LLMResponse


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Rate limit exceeded")
        return {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                        "tool_calls": [
                            {
                                "id": "tool_call_123",
                                "type": "function",
                                "function": {
                                    "name": "search_media",
                                    "arguments": "{\"q\":\"jay\"}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }


@pytest.mark.asyncio
async def test_chat_parses_tool_calls_and_usage() -> None:
    fake = FakeLLM()
    client = LLMClient(completion_fn=fake.complete)
    client._CHAT_RETRY_DELAYS = (0,)

    response = await client.chat(messages=[{"role": "user", "content": "hi"}])

    assert isinstance(response, LLMResponse)
    assert response.content == "ok"
    assert response.finish_reason == "tool_calls"
    assert response.usage["total_tokens"] == 5
    assert response.tool_calls[0].name == "search_media"
    assert response.tool_calls[0].arguments["q"] == "jay"


@pytest.mark.asyncio
async def test_chat_error_returns_error_response() -> None:
    async def fail(**kwargs: Any) -> Dict[str, Any]:
        raise RuntimeError("bad gateway")

    client = LLMClient(completion_fn=fail)
    client._CHAT_RETRY_DELAYS = (0,)

    response = await client.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.finish_reason == "error"
    assert "Error calling LLM" in (response.content or "")


@pytest.mark.asyncio
async def test_chat_stream_emits_text_delta() -> None:
    async def stream(**kwargs: Any):
        yield {"choices": [{"delta": {"content": "he"}}]}
        yield {"choices": [{"delta": {"content": "llo"}}], "usage": {"total_tokens": 3}}

    client = LLMClient(stream_fn=stream)
    events = []
    async for event in client.chat_stream(messages=[{"role": "user", "content": "hi"}]):
        events.append(event)

    assert [e["data"]["content"] for e in events] == ["he", "llo"]
    assert events[-1]["data"]["usage"]["total_tokens"] == 3

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from src.agent.context.summarizer import ProgressiveSummarizer


@dataclass
class FakeResponse:
    content: Optional[str]


class FakeLLMClient:
    def __init__(self) -> None:
        self.prompts: List[str] = []

    async def chat(self, messages: List[Dict[str, Any]]) -> FakeResponse:
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        return FakeResponse(content=f"summary-{len(self.prompts)}")


@pytest.mark.asyncio
async def test_progressive_summarizer_triggers_every_n() -> None:
    llm = FakeLLMClient()
    summarizer = ProgressiveSummarizer(llm_client=llm, summarize_every_n=2)

    await summarizer.add_turn(
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你？"},
    )
    assert summarizer.running_summary is None
    assert len(summarizer.unsummarized) == 2

    await summarizer.add_turn(
        {"role": "user", "content": "给我推荐音乐"},
        {"role": "assistant", "content": "推荐爵士乐"},
    )
    assert summarizer.running_summary == "summary-1"
    assert summarizer.unsummarized == []
    assert len(llm.prompts) == 1

    await summarizer.add_turn(
        {"role": "user", "content": "谢谢"},
        {"role": "assistant", "content": "不客气"},
    )
    assert len(summarizer.unsummarized) == 2
    assert summarizer.get_context()[1] == summarizer.unsummarized[-6:]


@pytest.mark.asyncio
async def test_progressive_summarizer_merges_running_summary() -> None:
    llm = FakeLLMClient()
    summarizer = ProgressiveSummarizer(llm_client=llm, summarize_every_n=2)

    await summarizer.add_turn(
        {"role": "user", "content": "用户偏好爵士"},
        {"role": "assistant", "content": "记住了"},
    )
    await summarizer.add_turn(
        {"role": "user", "content": "再推荐一些"},
        {"role": "assistant", "content": "好的"},
    )

    await summarizer.add_turn(
        {"role": "user", "content": "补充偏好"},
        {"role": "assistant", "content": "收到"},
    )
    await summarizer.add_turn(
        {"role": "user", "content": "继续"},
        {"role": "assistant", "content": "完成"},
    )

    assert len(llm.prompts) == 2
    assert "现有摘要" in llm.prompts[1]
    assert "summary-1" in llm.prompts[1]
    assert summarizer.running_summary == "summary-2"


@pytest.mark.asyncio
async def test_progressive_summarizer_one_off_summary() -> None:
    llm = FakeLLMClient()
    summarizer = ProgressiveSummarizer(llm_client=llm, summarize_every_n=3)

    result = await summarizer.summarize(
        [
            {"role": "user", "content": "信息1"},
            {"role": "assistant", "content": "信息2"},
        ]
    )

    assert result == "summary-1"
    assert "将以下对话精炼为简洁摘要" in llm.prompts[0]

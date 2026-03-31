import asyncio
from typing import Dict, List

from src.agent.config import AgentConfig
from src.agent.context.assembler import ContextAssembler
from src.agent.types import AgentRole


def _fixed_token_counter(_: str) -> int:
    return 1000


def _make_message(role: str, content: str, section: str | None = None) -> Dict[str, str]:
    message: Dict[str, str] = {"role": role, "content": content}
    if section is not None:
        message["section"] = section
    return message


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls: List[List[Dict[str, str]]] = []

    async def summarize(self, messages: List[Dict[str, str]]) -> str:
        self.calls.append(messages)
        return "summary"


def test_context_assembler_order() -> None:
    """验证 ContextAssembler 分区顺序稳定。"""
    summarizer = FakeSummarizer()
    assembler = ContextAssembler(token_counter=_fixed_token_counter, summarizer=summarizer)

    system_core = [_make_message("system", "sys")]
    memory_context = [_make_message("system", "mem", section="memory_context")]
    conversation = [_make_message("user", "hi"), _make_message("assistant", "ok")]
    tool_results = [_make_message("tool", "tool")]

    assembled = assembler.assemble(system_core, memory_context, conversation, tool_results)
    roles = [msg["role"] for msg in assembled]

    assert roles == ["system", "system", "user", "assistant", "tool"]


def test_fit_to_budget_trims_sections() -> None:
    """验证 fit_to_budget 按预算裁剪各分区。"""
    summarizer = FakeSummarizer()
    assembler = ContextAssembler(token_counter=_fixed_token_counter, summarizer=summarizer)
    config = AgentConfig(
        agent_id="agent_main",
        role=AgentRole.MAIN,
        role_description="你是媒体搜索专家",
        goal="帮助用户找到内容",
        constraints=["保持简洁"],
        allowed_tools=["search_media"],
    )

    system_core = [_make_message("system", f"sys{i}") for i in range(3)]
    memory_context = [
        _make_message("system", f"mem{i}", section="memory_context") for i in range(3)
    ]
    conversation = [
        _make_message("user" if i % 2 == 0 else "assistant", f"msg{i}") for i in range(14)
    ]
    tool_call_ids = [f"call_{i}" for i in range(3, 6)]
    conversation.append(
        {
            "role": "assistant",
            "content": "tool_call",
            "tool_calls": [{"id": tool_call_id} for tool_call_id in tool_call_ids],
        }
    )
    tool_results = [
        {"role": "tool", "content": f"tool{i}", "tool_call_id": f"call_{i}"} for i in range(6)
    ]
    messages = assembler.assemble(system_core, memory_context, conversation, tool_results)

    trimmed = asyncio.run(assembler.fit_to_budget(messages, config))

    assert [msg["content"] for msg in trimmed[:2]] == ["[对话摘要] summary", "[工具摘要] summary"]
    assert [msg["content"] for msg in trimmed[2:5]] == ["mem0", "mem1", "mem2"]

    trimmed_conversation = trimmed[5:11]
    assert [msg["content"] for msg in trimmed_conversation[:5]] == [
        f"msg{i}" for i in range(9, 14)
    ]
    assert trimmed_conversation[5]["content"] == "tool_call"

    trimmed_tools = trimmed[11:]
    assert [msg["content"] for msg in trimmed_tools] == ["tool3", "tool4", "tool5"]
    assert all("role" in msg and "content" in msg for msg in trimmed)


def test_fit_to_budget_preserves_last_three_turns() -> None:
    """验证最近三轮对话完整保留。"""
    summarizer = FakeSummarizer()
    assembler = ContextAssembler(token_counter=_fixed_token_counter, summarizer=summarizer)
    config = AgentConfig(
        agent_id="agent_main",
        role=AgentRole.MAIN,
        role_description="你是媒体搜索专家",
        goal="帮助用户找到内容",
        constraints=["保持简洁"],
        allowed_tools=["search_media"],
    )

    conversation = [
        _make_message("user" if i % 2 == 0 else "assistant", f"turn{i}") for i in range(16)
    ]
    messages = assembler.assemble([], [], conversation, [])
    trimmed = asyncio.run(assembler.fit_to_budget(messages, config))

    trimmed_conversation = [msg for msg in trimmed if msg["role"] in ("user", "assistant")]
    assert [msg["content"] for msg in trimmed_conversation] == [
        f"turn{i}" for i in range(10, 16)
    ]

import pytest
from typing import Any, Dict, List

from openai import AsyncOpenAI

from config.setting import settings
from src.agent.config import AgentConfig
from src.agent.context.assembler import ContextAssembler
from src.agent.context.summarizer import ProgressiveSummarizer
from src.agent.delegation import DelegationHandler
from src.agent.llm.provider import LLMClient
from src.agent.tools.base import ToolDefinition
from src.agent.tools.registry import ToolRegistry
from src.agent.types import AgentRole, RequestContext


async def _completion_fn_builder() -> tuple[LLMClient, AsyncOpenAI]:
    api_key = settings.llm.deepseek_api_key
    base_url = settings.llm.deepseek_base_url
    model = settings.llm.deepseek_model
    if not api_key:
        return None, None
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def completion_fn(**kwargs: Any):
        kwargs.pop("api_key", None)
        kwargs.pop("api_base", None)
        return await client.chat.completions.create(**kwargs)

    llm = LLMClient(
        api_key=api_key,
        api_base=base_url,
        default_model=model,
        completion_fn=completion_fn,
    )
    return llm, client


@pytest.mark.asyncio
async def test_p3_context_budget_with_real_llm(mongo_connection, override_get_redis_client):
    llm, _client = await _completion_fn_builder()
    if llm is None:
        pytest.skip("DEEPSEEK_API_KEY not found in settings. Skipping P3 E2E test.")

    summarizer = ProgressiveSummarizer(llm_client=llm, summarize_every_n=1)
    assembler = ContextAssembler(token_counter=lambda _: 3000, summarizer=summarizer)
    config = AgentConfig(
        agent_id="agent_p3_e2e",
        role=AgentRole.MAIN,
        role_description="测试上下文预算",
        goal="验证摘要与保留最近对话",
        constraints=[],
        allowed_tools=[],
    )

    conversation: List[Dict[str, Any]] = []
    for i in range(12):
        role = "user" if i % 2 == 0 else "assistant"
        conversation.append({"role": role, "content": f"turn-{i}"})

    messages = assembler.assemble([], [], conversation, [])
    trimmed = await assembler.fit_to_budget(messages, config)

    has_summary = any(
        msg.get("role") == "system" and str(msg.get("content", "")).startswith("[对话摘要]")
        for msg in trimmed
    )
    assert has_summary

    tail_expected = [msg["content"] for msg in conversation[-3:]]
    tail_actual = [
        msg["content"]
        for msg in trimmed
        if msg.get("role") in ("user", "assistant")
    ][-3:]
    assert tail_actual == tail_expected


@pytest.mark.asyncio
async def test_p3_delegation_e2e_with_real_llm(
    mongo_connection, test_seeder, override_get_redis_client
):
    llm, _client = await _completion_fn_builder()
    if llm is None:
        pytest.skip("DEEPSEEK_API_KEY not found in settings. Skipping P3 E2E test.")

    async def echo_tool(text: str, ctx: RequestContext) -> str:
        return f"{ctx.user_id}:{text}"

    async def delegate_schema_tool(**_: Any) -> str:
        return "ok"

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="delegate",
            description="将任务委派给子智能体。",
            parameters={
                "type": "object",
                "properties": {
                    "task_description": {"type": "string"},
                    "context": {"type": "string"},
                    "expected_output": {"type": "string"},
                    "required_tools": {"type": "array", "items": {"type": "string"}},
                    "specialist_type": {"type": "string"},
                },
                "required": ["task_description", "context", "expected_output"],
            },
            handler=delegate_schema_tool,
            category="delegation",
        )
    )
    registry.register(
        ToolDefinition(
            name="echo",
            description="回显输入文本。",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            handler=echo_tool,
            category="test",
        )
    )

    handler = DelegationHandler(tool_registry=registry, llm_client=llm)
    user = test_seeder.users["爱吃香菜"]
    ctx = RequestContext(user_id=str(user.id), session_id="p3-e2e", trace_id="p3-e2e")

    result = await handler.handle(
        task_description="总结用户最近的需求并提出下一步建议。",
        context="用户在整理媒体库信息，并希望得到下一步操作建议。",
        expected_output="给出简洁的总结和下一步建议。",
        ctx=ctx,
        required_tools=["echo"],
        specialist_type="general",
    )

    assert "子智能体结果" in result
    assert "输出" in result

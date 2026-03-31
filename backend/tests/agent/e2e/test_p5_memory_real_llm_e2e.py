import asyncio
from typing import Any, List

import pytest
from openai import AsyncOpenAI

from config.setting import settings
from src.agent.llm.provider import LLMClient
from src.agent.lotus_agent import LotusAgent
from src.agent.types import RequestContext
from src.agent.memory.models import MemoryCategory, MemoryItem, MemoryTier
from src.clients.ollama_embedding_client import get_text_embedding_async


async def _completion_fn_builder() -> tuple[LLMClient | None, AsyncOpenAI | None]:
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


async def _embedding_ready() -> bool:
    try:
        vectors = await get_text_embedding_async(["记忆系统连通性检查"])
    except Exception:
        return False
    if not vectors:
        return False
    return bool(vectors[0])


def _has_preference_text(text: str) -> bool:
    lowered = text.lower()
    return "科幻" in text or "sci-fi" in lowered or "sci fi" in lowered


async def _wait_for_memory(store, user_id: str, keyword_check, attempts: int = 8, delay: float = 0.6):
    items = []
    for _ in range(attempts):
        items = await store.get_user_memories(user_id=user_id)
        if any(keyword_check(item.content or "") for item in items):
            return items
        await asyncio.sleep(delay)
    return items


@pytest.mark.asyncio
async def test_p5_memory_e2e_real_llm(mongo_connection, test_env_settings, override_get_redis_client):
    llm, _client = await _completion_fn_builder()
    if llm is None:
        pytest.skip("DEEPSEEK_API_KEY not found in settings. Skipping P5 E2E test.")

    if not await _embedding_ready():
        pytest.skip("Ollama embedding not available. Skipping P5 E2E test.")

    agent = LotusAgent(llm_client=llm)
    memory_runtime = agent.memory_runtime
    extractor = await memory_runtime.get_extractor()
    extractor.extract_every_n = 1
    store = await memory_runtime.get_store()
    retriever = await memory_runtime.get_retriever()

    session_id = "p5-e2e-session"
    user_id = "p5-e2e-user"

    turn_sets = [
        [
            {"role": "user", "content": "我喜欢科幻片", "turn_id": "1"},
            {"role": "assistant", "content": "了解", "turn_id": "2"},
            {"role": "user", "content": "以后推荐电影优先科幻", "turn_id": "3"},
        ],
        [
            {"role": "user", "content": "请记住：我的偏好是喜欢科幻电影", "turn_id": "1"},
            {"role": "assistant", "content": "好的，我会记住", "turn_id": "2"},
            {"role": "user", "content": "以后推荐科幻相关电影", "turn_id": "3"},
        ],
    ]
    user_mems = []
    for turns in turn_sets:
        await extractor._run_extraction(session_id, user_id, turns)
        user_mems = await _wait_for_memory(store, user_id, lambda _: True)
        if user_mems:
            break

    assert user_mems
    print(f"[DEBUG] Extracted user_mems: {user_mems}")
    preference_mems = [
        item for item in user_mems if item.category == MemoryCategory.PREFERENCE and item.content
    ]
    if preference_mems:
        assert any(_has_preference_text(item.content or "") for item in preference_mems)
    target = preference_mems[0].content if preference_mems else next(
        (item.content for item in user_mems if item.content), ""
    )
    print(f"\n[DEBUG] Extracted user_mems: {[m.content for m in user_mems]}")
    print(f"[DEBUG] target for retrieval: {target}")
    assert target

    assembled = await retriever.retrieve_for_context(
        query=target,
        user_id=user_id,
        session_id=session_id,
    )
    print(f"[DEBUG] retrieved assembled: {assembled}")
    assert assembled.user
    user_mem_ids = {item.memory_id for item in user_mems}
    assert any(item.memory_id in user_mem_ids for item in assembled.user)

    ctx = RequestContext(user_id=user_id, session_id=session_id, trace_id="p5-e2e")
    messages = await agent._loop.context_builder.build_messages(target, history=None, ctx=ctx)
    system_contents: List[str] = [
        str(m.get("content", "")) for m in messages if m.get("role") == "system"
    ]
    assert any(
        ("用户画像摘要" in content or "相关用户记忆" in content) and target in content
        for content in system_contents
    )

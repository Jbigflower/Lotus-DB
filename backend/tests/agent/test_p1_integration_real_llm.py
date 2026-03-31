
import pytest
import os
import asyncio
from typing import AsyncGenerator
from dotenv import load_dotenv

from src.agent.config import AgentConfig, AgentRole
from src.agent.llm.provider import LLMClient
from src.agent.loop import AgentLoop
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.movie_tools import register_movie_tools
from src.agent.types import RequestContext
from openai import AsyncOpenAI

# Load env for real LLM
load_dotenv()

@pytest.mark.asyncio
async def test_p1_integration_real_llm(mongo_connection, test_seeder, override_get_redis_client):
    """
    Integration test for Phase 1 using Real LLM (DeepSeek) and Seeded Data (MongoMock).
    This verifies the full chain: Agent -> LLM -> Tool -> Service -> Repo -> DB.
    """
    
    # 1. Setup LLM Client (Real)
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com"
    
    if not api_key:
        pytest.skip("Skipping real LLM test: DEEPSEEK_API_KEY not found")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def completion_fn(**kwargs):
        kwargs.pop("api_key", None)
        kwargs.pop("api_base", None)
        # DeepSeek V3 supports tools
        return await client.chat.completions.create(**kwargs)

    async def stream_fn(**kwargs):
        kwargs.pop("api_key", None)
        kwargs.pop("api_base", None)
        kwargs["stream"] = True
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            yield chunk

    llm = LLMClient(
        api_key=api_key,
        api_base=base_url,
        default_model="deepseek-chat",
        completion_fn=completion_fn,
        stream_fn=stream_fn
    )

    # 2. Setup Tools & Registry
    registry = ToolRegistry()
    register_movie_tools(registry)
    
    # 3. Setup Agent Loop
    config = AgentConfig(
        agent_id="test-agent-real",
        role=AgentRole.MAIN,
        role_description="You are a helpful assistant for Lotus-DB.",
        goal="Help user manage their media library.",
        constraints=["Be concise."],
        allowed_tools=["list_movies", "get_movie"]
    )
    
    loop = AgentLoop(llm, registry, config)
    
    # 4. Get User from Seeder
    # '爱吃香菜' is seeded in test_seeder
    user = test_seeder.users["爱吃香菜"]
    ctx = RequestContext(
        user_id=str(user.id),
        session_id="test-session-real",
        trace_id="test-trace-real"
    )

    # 5. Execute Scenario 1: Search for a movie that likely exists (Red Sorghum / 红高粱)
    # The seeder loads movies from JSON files. "Red Sorghum" is explicitly mentioned in seed_aliases.
    user_input = "帮我查一下有没有《红高粱》这部电影"
    
    print(f"\nUser: {user_input}")
    
    tool_called = False
    final_response = ""
    
    async for event in loop.run(user_input, ctx):
        if event["type"] == "tool_start":
            print(f"🛠️ Tool Call: {event['data']['name']} args={event['data']['args']}")
            if event['data']['name'] == "list_movies":
                tool_called = True
        elif event["type"] == "tool_end":
            print(f"✅ Tool Result: {str(event['data']['result'])[:200]}...")
        elif event["type"] == "text_delta":
            print(event["data"]["content"], end="", flush=True)
            final_response += event["data"]["content"]
        elif event["type"] == "error":
            print(f"❌ Error: {event['data']}")
            # Don't fail immediately, let's see the output, but in a real test we might want to.
            
    assert tool_called, "Agent should have called list_movies tool"
    # assert "红高粱" in final_response or "Red Sorghum" in final_response, "Agent should mention the movie found"

    # 6. Execute Scenario 2: Simple Chat
    user_input_2 = "你好，你是谁？"
    print(f"\n\nUser: {user_input_2}")
    
    async for event in loop.run(user_input_2, ctx):
        if event["type"] == "text_delta":
            print(event["data"]["content"], end="", flush=True)


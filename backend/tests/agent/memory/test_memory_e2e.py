
import asyncio
import os
import pytest
import litellm
from typing import List, Dict, Any
from datetime import datetime

from config.setting import settings
from src.agent.llm.provider import LLMClient
from src.agent.memory.models import MemoryItem, MemoryStatus, MemoryTier
from src.agent.memory.store import MemoryStoreFacade
from src.agent.memory.retriever import MemoryRetriever
from src.agent.memory.extraction import ExtractionPipeline
from src.agent.memory.conflict import ConflictResolver

# Ensure we use the lancedb package
import lancedb

# Mock Embedding Function for controlled conflict testing
async def mock_embedding_fn(text: str) -> List[float]:
    # Simple deterministic embedding for testing
    # Dimension = 128 (to be somewhat realistic, though we only care about similarity)
    # We use a simple logic:
    # - "Jazz" -> Base vector A
    # - "Hate" -> Modifier
    # - "Coding" -> Base vector B
    
    vec = [0.0] * 128
    
    text_lower = text.lower()
    if "jazz" in text_lower or "爵士" in text_lower:
        # Base vector for Jazz: mostly index 0
        vec[0] = 1.0
        if "hate" in text_lower or "noisy" in text_lower or "讨厌" in text_lower or "吵" in text_lower:
            # "Hate Jazz" is similar to "Love Jazz" in topic, but we want it to be 
            # in the "Conflict Zone" (0.6 < sim < 0.92).
            # If we make it [0.8, 0.6, ...], cosine sim will be ~0.8
            vec[0] = 0.8
            vec[1] = 0.6
        else:
            # "Love Jazz"
            vec[0] = 1.0
            vec[1] = 0.1
    elif "coding" in text_lower:
        # Orthogonal to Jazz
        vec[2] = 1.0
    else:
        # Random/Other
        vec[3] = 1.0
        
    # Normalize
    norm = sum(x**2 for x in vec) ** 0.5
    return [x/norm for x in vec]

@pytest.mark.asyncio
async def test_memory_e2e_with_real_llm(mongo_connection):
    """
    End-to-End Test for Memory System using Real LLM (DeepSeek) and Real/Mocked DBs.
    Requires DEEPSEEK_API_KEY in .env or settings.
    """
    api_key = settings.llm.deepseek_api_key
    base_url = settings.llm.deepseek_base_url
    model = settings.llm.deepseek_model

    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY not found in settings. Skipping E2E test.")

    print(f"\n[E2E] Starting Memory System Test with Model: {model}")

    # 1. Setup Infrastructure
    # Mongo is already mocked via mongo_connection fixture and src.db.mongo_db.MongoManager
    from src.db.mongo_db import get_mongo_db
    mongo_db = get_mongo_db()
    collection = mongo_db["memories"]
    
    # Setup LanceDB (Use a temporary local DB)
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db = lancedb.connect(tmpdir)
        try:
            table = db.create_table(
                "memories",
                data=[{
                    "memory_id": "init", 
                    "vector": [0.0]*128, 
                    "tier": "user", 
                    "user_id": "u1", 
                    "status": "active", 
                    "category": "fact"
                }],
                mode="overwrite"
            )
        except Exception:
            # Fallback for older lancedb versions if schema inference fails on empty
             table = db.create_table(
                "memories",
                data=[{
                    "memory_id": "init", 
                    "vector": [0.0]*128, 
                    "tier": "user", 
                    "user_id": "u1", 
                    "status": "active", 
                    "category": "fact"
                }]
            )

        # 2. Setup Components
        litellm.set_verbose = True
        store = MemoryStoreFacade(collection, table, mock_embedding_fn)
        
        # Real LLM Client
        async def real_completion_fn(**kwargs):
            try:
                # Map LLMClient args to litellm args
                if "api_key" not in kwargs:
                    kwargs["api_key"] = api_key
                if "api_base" not in kwargs and base_url:
                    kwargs["api_base"] = base_url
                
                # litellm expects 'model'
                if "model" not in kwargs:
                    kwargs["model"] = model
                
                # Force openai/ prefix to treat as OpenAI-compatible endpoint
                if not kwargs["model"].startswith("openai/") and not kwargs["model"].startswith("deepseek/"):
                     kwargs["model"] = f"openai/{kwargs['model']}"
                
                print(f"[E2E] Calling LLM: {kwargs.get('model')} at {kwargs.get('api_base')}")
                resp = await litellm.acompletion(**kwargs)
                print(f"[E2E] LLM Response: {resp}")
                return resp
            except Exception as e:
                print(f"[E2E] LLM Call Failed: {e}")
                raise e

        llm_client = LLMClient(
            api_key=api_key,
            api_base=base_url,
            default_model=model,
            completion_fn=real_completion_fn
        )
        
        resolver = ConflictResolver(store, llm_client, mock_embedding_fn)
        # We hook resolver into extraction pipeline manually or via modification
        # The current ExtractionPipeline has an optional conflict_resolver
        extraction = ExtractionPipeline(
            llm_client=llm_client, 
            store=store, 
            conflict_resolver=resolver,
            extract_every_n=1 # Extract immediately for test
        )
        
        retriever = MemoryRetriever(store, mock_embedding_fn)

        # 3. Execution - Step 1: User Expresses Preference
        user_id = "user_e2e_001"
        session_id = "session_e2e_001"
        
        print("[E2E] Step 1: User says 'I love Jazz music'")
        turns = [
            {"role": "user", "content": "Hello, I really love Jazz music, it's my absolute favorite genre.", "turn_id": "t1"}
        ]
        
        # Trigger Extraction
        await extraction.on_turn_complete(session_id, user_id, turns)
        
        # Wait for async task (ExtractionPipeline uses asyncio.create_task)
        # In test, we need to wait a bit or verify side effects
        await asyncio.sleep(10) # Give LLM time to respond
        
        # Verify Storage
        memories = await store.get_user_memories(user_id)
        print(f"[E2E] Stored Memories after Step 1: {len(memories)}")
        for m in memories:
            print(f" - {m.content} [{m.category}]")
            
        assert len(memories) >= 1
        jazz_memory = next((m for m in memories if "jazz" in m.content.lower()), None)
        assert jazz_memory is not None
        assert jazz_memory.status == MemoryStatus.ACTIVE

        table.add(
            [
                {
                    "memory_id": m.memory_id,
                    "vector": m.embedding or (await mock_embedding_fn(m.content)),
                    "tier": m.tier.value,
                    "user_id": m.user_id,
                    "status": m.status.value,
                    "category": m.category.value,
                }
                for m in memories
            ]
        )

        # 4. Execution - Step 2: Context Retrieval
        print("[E2E] Step 2: Retrieving context for 'Recommend music'")
        context = await retriever.retrieve_for_context(
            query="Recommend me some music",
            user_id=user_id,
            session_id=session_id
        )
        print(f"[E2E] Retrieved User Memories: {len(context.user)}")
        assert len(context.user) > 0
        assert context.user[0].memory_id == jazz_memory.memory_id

        # 5. Execution - Step 3: Conflict (Contradiction)
        print("[E2E] Step 3: User says 'I hate Jazz now'")
        new_turns = [
            {"role": "user", "content": "Actually, I hate Jazz now. It's too noisy for me.", "turn_id": "t2"}
        ]
        
        # We manually trigger conflict resolution flow via extraction
        # Since we set extract_every_n=1, this should trigger extraction again
        # The new turn count for session needs to increase
        await extraction.on_turn_complete(session_id, user_id, new_turns)

        print("[E2E] Waiting 30s for Extraction + Conflict Resolution...")
        await asyncio.sleep(30) # Wait for LLM (Extraction + Conflict Check)

        # Verify Conflict Resolution
        memories_after = await store.get_user_memories(user_id, status=MemoryStatus.ACTIVE)
        all_memories = await store.get_user_memories(user_id, status=MemoryStatus.SUPERSEDED) # Get superseded too? 
        # get_user_memories filters by status=ACTIVE by default
        
        print(f"[E2E] Active Memories after Step 3: {len(memories_after)}")
        for m in memories_after:
            print(f" - {m.content}")

        # Check if old memory is superseded
        old_mem_check = await collection.find_one({"memory_id": jazz_memory.memory_id})
        print(f"[E2E] Old Memory Status: {old_mem_check['status']}")
        
        assert old_mem_check['status'] == MemoryStatus.SUPERSEDED.value
        assert old_mem_check['superseded_by'] is not None
        
        # Check if new memory is active
        hate_memory = next((m for m in memories_after if "hate" in m.content.lower() or "noisy" in m.content.lower() or "讨厌" in m.content or "吵" in m.content), None)
        assert hate_memory is not None
        assert hate_memory.status == MemoryStatus.ACTIVE
        
        print("[E2E] Test Passed Successfully!")

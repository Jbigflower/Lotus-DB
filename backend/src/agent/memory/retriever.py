from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, List

from .models import MemoryItem, MemoryStatus, MemoryTier
from .store import MemoryStoreFacade


@dataclass
class AssembledMemory:
    """组装后的记忆结果。"""

    session: List[MemoryItem]
    user: List[MemoryItem]
    agent: List[MemoryItem]


class MemoryRetriever:
    """记忆检索器，负责组装上下文所需记忆。"""

    def __init__(
        self,
        store: MemoryStoreFacade,
        embedding_fn: Callable[[str], Awaitable[List[float]]],
    ) -> None:
        self._store = store
        self._embedding_fn = embedding_fn

    async def retrieve_for_context(
        self,
        query: str,
        user_id: str,
        session_id: str,
        agent_top_k: int = 5,
        user_top_k: int = 10,
    ) -> AssembledMemory:
        """检索并组装会话、用户与 Agent 记忆。"""

        query_embedding = await self._embedding_fn(query)
        session_memories = await self._store.get_session_memories(session_id)

        user_candidates = await self._store.search_semantic(
            query_embedding=query_embedding,
            tier=MemoryTier.USER,
            user_id=user_id,
            status=MemoryStatus.ACTIVE,
            top_k=user_top_k * 3,
        )
        user_memories = self._rerank_user_memories(user_candidates, user_top_k)
        for mem in user_memories:
            asyncio.create_task(self._store.touch(mem.memory_id))

        agent_memories = await self._store.search_semantic(
            query_embedding=query_embedding,
            tier=MemoryTier.AGENT,
            status=MemoryStatus.ACTIVE,
            top_k=agent_top_k,
        )

        return AssembledMemory(
            session=session_memories,
            user=user_memories,
            agent=agent_memories,
        )

    def _rerank_user_memories(
        self,
        memories: List[MemoryItem],
        top_k: int,
    ) -> List[MemoryItem]:
        now = datetime.now(timezone.utc)
        scored: List[tuple[float, MemoryItem]] = []
        total = max(len(memories), 1)
        for rank, memory in enumerate(memories):
            score = self._compute_score(memory, rank, total, now)
            setattr(memory, "final_score", score)
            scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:top_k]]

    def _compute_score(
        self,
        memory: MemoryItem,
        rank: int,
        total: int,
        now: datetime,
    ) -> float:
        rank_score = 1.0 - (rank / max(total - 1, 1))
        last_accessed = memory.last_accessed_at or memory.created_at
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=timezone.utc)
        hours_since = max((now - last_accessed).total_seconds(), 0.0) / 3600.0
        recency = math.exp(-0.01 * hours_since)
        frequency = math.log1p(memory.access_count) / math.log1p(100)
        confidence = memory.confidence
        similarity = getattr(memory, "similarity_score", rank_score)
        return (
            0.4 * similarity
            + 0.2 * recency
            + 0.2 * confidence
            + 0.2 * frequency
        )

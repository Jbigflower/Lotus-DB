from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest
from mongomock_motor import AsyncMongoMockClient

from src.agent.memory.models import MemoryCategory, MemoryItem, MemoryStatus, MemoryTier
from src.agent.memory.retriever import MemoryRetriever
from src.agent.memory.store import MemoryStoreFacade


class FakeLanceQuery:
    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self._records = records
        self._expr: Optional[str] = None
        self._limit: Optional[int] = None

    def where(self, expr: str) -> "FakeLanceQuery":
        self._expr = expr
        return self

    def limit(self, n: int) -> "FakeLanceQuery":
        self._limit = n
        return self

    async def to_list(self) -> List[Dict[str, Any]]:
        records = self._apply_filter(self._records)
        if self._limit is not None:
            records = records[: self._limit]
        return records

    def _apply_filter(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self._expr:
            return records
        clauses = [c.strip() for c in self._expr.split("AND")]

        def match(record: Dict[str, Any]) -> bool:
            for clause in clauses:
                if "=" not in clause:
                    continue
                left, right = clause.split("=", 1)
                key = left.strip()
                value = right.strip().strip("'")
                if str(record.get(key)) != value:
                    return False
            return True

        return [record for record in records if match(record)]


class FakeLanceTable:
    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []

    def add(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            record = dict(item)
            record.setdefault("_distance", 0.2)
            self.records.append(record)

    def search(self, _: List[float]) -> FakeLanceQuery:
        return FakeLanceQuery(self.records)

    def update(
        self,
        updates: Dict[str, Any] | None = None,
        where: str = "",
        values: Dict[str, Any] | None = None,
    ) -> None:
        payload = values if values is not None else (updates or {})
        if "=" not in where:
            return
        left, right = where.split("=", 1)
        key = left.strip()
        value = right.strip().strip("'")
        for record in self.records:
            if str(record.get(key)) == value:
                record.update(payload)


@pytest.mark.asyncio
async def test_retrieve_for_context_assembles_memories() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(_: str) -> List[float]:
        return [0.2, 0.4]

    store = MemoryStoreFacade(collection, lance, embed)
    retriever = MemoryRetriever(store, embed)

    session_item = MemoryItem(
        memory_id="s1",
        tier=MemoryTier.SESSION,
        user_id="u1",
        session_id="session-1",
        category=MemoryCategory.FACT,
        content="会话记忆",
    )
    user_item_a = MemoryItem(
        memory_id="u1a",
        tier=MemoryTier.USER,
        user_id="u1",
        category=MemoryCategory.PREFERENCE,
        content="喜欢爵士乐",
        confidence=0.2,
    )
    user_item_b = MemoryItem(
        memory_id="u1b",
        tier=MemoryTier.USER,
        user_id="u1",
        category=MemoryCategory.PREFERENCE,
        content="喜欢摇滚",
        confidence=0.9,
        last_accessed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        access_count=5,
    )
    agent_item = MemoryItem(
        memory_id="a1",
        tier=MemoryTier.AGENT,
        category=MemoryCategory.KNOWLEDGE,
        content="Agent 记忆",
    )

    await collection.insert_many(
        [
            session_item.to_dict(),
            user_item_a.to_dict(),
            user_item_b.to_dict(),
            agent_item.to_dict(),
        ]
    )

    lance.add(
        [
            {
                "memory_id": "u1a",
                "vector": [0.1],
                "tier": MemoryTier.USER.value,
                "user_id": "u1",
                "status": MemoryStatus.ACTIVE.value,
                "category": MemoryCategory.PREFERENCE.value,
                "_distance": 0.4,
            },
            {
                "memory_id": "u1b",
                "vector": [0.1],
                "tier": MemoryTier.USER.value,
                "user_id": "u1",
                "status": MemoryStatus.ACTIVE.value,
                "category": MemoryCategory.PREFERENCE.value,
                "_distance": 0.1,
            },
            {
                "memory_id": "a1",
                "vector": [0.1],
                "tier": MemoryTier.AGENT.value,
                "user_id": None,
                "status": MemoryStatus.ACTIVE.value,
                "category": MemoryCategory.KNOWLEDGE.value,
                "_distance": 0.2,
            },
        ]
    )

    assembled = await retriever.retrieve_for_context(
        query="推荐音乐",
        user_id="u1",
        session_id="session-1",
        agent_top_k=1,
        user_top_k=1,
    )

    assert len(assembled.session) == 1
    assert assembled.session[0].memory_id == "s1"
    assert len(assembled.user) == 1
    assert assembled.user[0].memory_id == "u1b"
    assert len(assembled.agent) == 1
    assert assembled.agent[0].memory_id == "a1"

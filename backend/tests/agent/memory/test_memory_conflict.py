from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
from mongomock_motor import AsyncMongoMockClient

from src.agent.memory.conflict import ConflictResolver
from src.agent.memory.models import MemoryCategory, MemoryItem, MemoryStatus, MemoryTier
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
            self.records.append(dict(item))

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


@dataclass
class FakeLLMResponse:
    content: Optional[str]


class FakeLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    async def chat(self, **_: Any) -> FakeLLMResponse:
        return FakeLLMResponse(content=self._content)


@pytest.mark.asyncio
async def test_conflict_resolver_marks_superseded() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(_: str) -> List[float]:
        return [0.1, 0.2]

    existing = MemoryItem(
        memory_id="m1",
        tier=MemoryTier.USER,
        user_id="u1",
        category=MemoryCategory.PREFERENCE,
        content="喜欢流行乐",
    )
    await collection.insert_one(existing.to_dict())
    lance.add(
        [
            {
                "memory_id": "m1",
                "vector": [0.1],
                "tier": MemoryTier.USER.value,
                "user_id": "u1",
                "status": MemoryStatus.ACTIVE.value,
                "category": MemoryCategory.PREFERENCE.value,
                "_distance": 0.2,
            }
        ]
    )

    llm = FakeLLMClient('{"action":"contradiction"}')
    store = MemoryStoreFacade(collection, lance, embed)
    resolver = ConflictResolver(store=store, llm_client=llm, embedding_fn=embed)

    new_item = MemoryItem(
        memory_id="m2",
        tier=MemoryTier.USER,
        user_id="u1",
        category=MemoryCategory.PREFERENCE,
        content="不太喜欢流行乐了",
    )
    await resolver.resolve_and_store(new_item)

    old_doc = await collection.find_one({"memory_id": "m1"})
    new_doc = await collection.find_one({"memory_id": "m2"})
    assert old_doc is not None
    assert new_doc is not None
    assert old_doc["status"] == MemoryStatus.SUPERSEDED.value
    assert old_doc["superseded_by"] == "m2"

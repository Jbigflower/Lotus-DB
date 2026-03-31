from typing import Any, Dict, List, Optional

import pytest
from mongomock_motor import AsyncMongoMockClient

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
        self.last_update_payload: Optional[Dict[str, Any]] = None
        self.last_update_where: Optional[str] = None
        self.last_update_used: Optional[str] = None

    def add(self, items: List[Dict[str, Any]]) -> None:
        for item in items:
            record = dict(item)
            record.setdefault("_distance", 0.1)
            self.records.append(record)

    def search(self, _: List[float]) -> FakeLanceQuery:
        return FakeLanceQuery(self.records)

    def update(
        self,
        updates: Dict[str, Any] | None = None,
        where: str = "",
        values: Dict[str, Any] | None = None,
    ) -> None:
        if values is not None:
            payload = values
            self.last_update_used = "values"
        else:
            payload = updates or {}
            self.last_update_used = "updates"
        self.last_update_payload = dict(payload)
        self.last_update_where = where
        if "=" not in where:
            return
        left, right = where.split("=", 1)
        key = left.strip()
        value = right.strip().strip("'")
        for record in self.records:
            if str(record.get(key)) == value:
                record.update(payload)


@pytest.mark.asyncio
async def test_memory_item_roundtrip() -> None:
    item = MemoryItem(
        tier=MemoryTier.USER,
        user_id="u1",
        session_id="s1",
        category=MemoryCategory.PREFERENCE,
        content="喜欢爵士乐",
        entities=["爵士乐"],
        confidence=0.8,
        status=MemoryStatus.ACTIVE,
    )
    doc = item.to_dict()
    rebuilt = MemoryItem.from_dict(doc)
    assert rebuilt.memory_id == item.memory_id
    assert rebuilt.tier == MemoryTier.USER
    assert rebuilt.category == MemoryCategory.PREFERENCE
    assert rebuilt.content == "喜欢爵士乐"


@pytest.mark.asyncio
async def test_memory_store_writes_mongo_only() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(text: str) -> List[float]:
        return [0.1, float(len(text))]

    store = MemoryStoreFacade(collection, lance, embed)
    item = MemoryItem(
        tier=MemoryTier.USER,
        user_id="u1",
        session_id="s1",
        category=MemoryCategory.PREFERENCE,
        content="喜欢爵士乐",
    )
    memory_id = await store.add(item)
    mongo_doc = await collection.find_one({"memory_id": memory_id})
    assert mongo_doc is not None
    assert not lance.records


@pytest.mark.asyncio
async def test_memory_store_update_writes_mongo_only() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(text: str) -> List[float]:
        return [0.5, float(len(text))]

    store = MemoryStoreFacade(collection, lance, embed)
    item = MemoryItem(
        tier=MemoryTier.USER,
        user_id="u1",
        session_id="s1",
        category=MemoryCategory.FACT,
        content="原始内容",
    )
    memory_id = await store.add(item)
    item.category = MemoryCategory.PREFERENCE
    item.tier = MemoryTier.USER
    item.status = MemoryStatus.ARCHIVED
    item.content = "更新内容"
    item.embedding = None
    await store.update(item)

    mongo_doc = await collection.find_one({"memory_id": memory_id})
    assert mongo_doc is not None
    assert mongo_doc["content"] == "更新内容"
    assert mongo_doc["category"] == MemoryCategory.PREFERENCE.value
    assert mongo_doc["status"] == MemoryStatus.ARCHIVED.value
    assert lance.last_update_used is None


@pytest.mark.asyncio
async def test_search_semantic_preserves_order() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(_: str) -> List[float]:
        return [0.2, 0.3]

    item_one = MemoryItem(
        memory_id="m1",
        tier=MemoryTier.USER,
        user_id="u1",
        category=MemoryCategory.FACT,
        content="第一条",
    )
    item_two = MemoryItem(
        memory_id="m2",
        tier=MemoryTier.USER,
        user_id="u1",
        category=MemoryCategory.FACT,
        content="第二条",
    )
    await collection.insert_many([item_one.to_dict(), item_two.to_dict()])
    lance.add(
        [
            {
                "memory_id": "m2",
                "vector": [0.1],
                "tier": MemoryTier.USER.value,
                "user_id": "u1",
                "status": MemoryStatus.ACTIVE.value,
                "category": MemoryCategory.FACT.value,
            },
            {
                "memory_id": "m1",
                "vector": [0.1],
                "tier": MemoryTier.USER.value,
                "user_id": "u1",
                "status": MemoryStatus.ACTIVE.value,
                "category": MemoryCategory.FACT.value,
            },
        ]
    )
    store = MemoryStoreFacade(collection, lance, embed)
    result = await store.search_semantic(
        [0.1],
        tier=MemoryTier.USER,
        user_id="u1",
        status=MemoryStatus.ACTIVE,
        top_k=2,
    )
    assert [item.memory_id for item in result] == ["m2", "m1"]

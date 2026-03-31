import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
from mongomock_motor import AsyncMongoMockClient

from src.agent.memory.extraction import ExtractionPipeline
from src.agent.memory.models import MemoryItem
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
        records = self._records
        if self._limit is not None:
            records = records[: self._limit]
        return records


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
async def test_extraction_pipeline_adds_memory() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(_: str) -> List[float]:
        return [0.1, 0.2]

    llm = FakeLLMClient(
        """
        [
          {
            "category": "preference",
            "content": "喜欢爵士乐",
            "confidence": "high",
            "source_turn_id": "t1",
            "entities": ["爵士乐"]
          }
        ]
        """
    )
    store = MemoryStoreFacade(collection, lance, embed)
    pipeline = ExtractionPipeline(llm_client=llm, store=store, extract_every_n=1)

    await pipeline.on_turn_complete(
        session_id="s1",
        user_id="u1",
        turns=[{"turn_id": "t1", "role": "user", "content": "我喜欢爵士乐"}],
    )
    await asyncio.sleep(0)

    doc = await collection.find_one({"user_id": "u1"})
    assert doc is not None
    assert doc["category"] == "preference"
    assert doc["content"] == "喜欢爵士乐"
    assert doc["tier"] == "user"


@pytest.mark.asyncio
async def test_extraction_pipeline_ignores_invalid_payload() -> None:
    client = AsyncMongoMockClient()
    collection = client["test_db"]["memories"]
    lance = FakeLanceTable()

    async def embed(_: str) -> List[float]:
        return [0.1, 0.2]

    llm = FakeLLMClient("not-json")
    store = MemoryStoreFacade(collection, lance, embed)
    pipeline = ExtractionPipeline(llm_client=llm, store=store)

    await pipeline.on_session_end(
        session_id="s1",
        user_id="u1",
        all_turns=[{"turn_id": "t1", "role": "user", "content": "我喜欢爵士乐"}],
    )
    await asyncio.sleep(0)

    doc = await collection.find_one({"user_id": "u1"})
    assert doc is None
    assert not lance.records

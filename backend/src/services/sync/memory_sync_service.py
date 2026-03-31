from typing import Any, Dict, List, Optional

import pyarrow as pa
from pydantic import BaseModel

from src.agent.memory.runtime import MemoryLanceSchema
from src.db.lance_db import get_lance_manager
from src.db.mongo_db import get_collection
from .base_sync_service import BaseSyncService


class MemorySyncModel(BaseModel):
    id: str
    memory_id: str
    vector: List[float]
    tier: str
    user_id: Optional[str]
    status: str
    category: str


class MemoryLanceRepo:
    def __init__(self) -> None:
        self._table = None

    async def _ensure_table(self):
        if self._table is None:
            manager = get_lance_manager()
            self._table = await manager.get_or_create_table(
                "memories", schema=MemoryLanceSchema
            )
        return self._table

    async def upsert(self, items: List[MemorySyncModel]) -> None:
        if not items:
            return
        table = await self._ensure_table()
        records = [
            {
                "memory_id": item.memory_id,
                "vector": item.vector,
                "tier": item.tier,
                "user_id": item.user_id,
                "status": item.status,
                "category": item.category,
            }
            for item in items
        ]
        schema = await table.schema()
        data = pa.Table.from_pylist(records, schema=schema)
        await (
            table.merge_insert("memory_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(data)
        )

    async def delete(self, ids: List[str], soft: bool = False) -> None:
        if not ids:
            return
        table = await self._ensure_table()
        id_list = "','".join(ids)
        await table.delete(where=f"memory_id IN ('{id_list}')")


class MemorySyncService(BaseSyncService[MemorySyncModel]):
    """记忆集合 → LanceDB 同步服务"""

    def get_collection(self):
        return get_collection("memories")

    def get_target_repo(self):
        return MemoryLanceRepo()

    def to_model_in_db(self, doc: Dict[str, Any]) -> MemorySyncModel:
        memory_id = doc.get("memory_id") or doc.get("_id")
        memory_id_str = str(memory_id)
        return MemorySyncModel(
            id=memory_id_str,
            memory_id=memory_id_str,
            vector=doc.get("embedding") or [],
            tier=str(doc.get("tier") or ""),
            user_id=doc.get("user_id"),
            status=str(doc.get("status") or ""),
            category=str(doc.get("category") or ""),
        )

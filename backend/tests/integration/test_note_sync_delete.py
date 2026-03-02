import pytest
import pandas as pd

from src.db.lance_db import init_lance, close_lance
from src.services.sync.note_sync_service import NoteSyncService
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo
from lancedb.pydantic import LanceModel, Vector
from src.models import NoteInDB


class NoteSchema2(LanceModel):
    id: str
    vector: Vector(768)
    document: str
    parent_id: str
    chunk_index: int
    user_id: str
    is_deleted: bool


class PatchedNoteRepo(BaseLanceRepo):
    def __init__(self):
        super().__init__(table_name="notes")
        self.soft_delete_flag = "is_deleted"

    def get_schema(self):
        return NoteSchema2

    async def to_lance_record(self, note: NoteInDB):
        return {
            "id": f"{note.id}_0",
            "vector": [0.1] * 768,
            "document": note.content or "",
            "parent_id": note.id,
            "chunk_index": 0,
            "user_id": note.user_id,
            "is_deleted": False,
        }

    async def batch_to_lance_records(self, notes):
        records = []
        for note in notes:
            records.append(
                {
                    "id": f"{note.id}_0",
                    "vector": [0.1] * 768,
                    "document": note.content or "",
                    "parent_id": note.id,
                    "chunk_index": 0,
                    "user_id": note.user_id,
                    "is_deleted": False,
                }
            )
        return records

    def from_lance_record(self, record):
        return record

    async def delete_by_parent_ids(self, parent_ids, soft=True):
        await self.ensure_table_bound()
        id_list = "','".join(parent_ids)
        if soft:
            await self.table.update(values={self.soft_delete_flag: True}, where=f"parent_id IN ('{id_list}')")
        else:
            await self.table.delete(where=f"parent_id IN ('{id_list}')")


@pytest.mark.asyncio
async def test_note_delete_soft_by_parent_id(tmp_path):
    from config.setting import settings
    settings.database.lancedb_path = str(tmp_path)
    await init_lance()

    svc = NoteSyncService()
    repo = PatchedNoteRepo()

    insert_change = {
        "operationType": "insert",
        "fullDocument": {
            "_id": "n1",
            "user_id": "u1",
            "movie_id": "m1",
            "title": "t",
            "content": "c",
            "tags": [],
            "is_deleted": False,
        },
    }
    await svc._handle_change(insert_change, repo)
    assert await repo.table.count_rows() == 1

    delete_change = {
        "operationType": "delete",
        "documentKey": {"_id": "n1"},
    }
    await svc._handle_change(delete_change, repo)

    results = await repo.table.query().where("parent_id = 'n1'").to_list()
    assert len(results) == 1
    row = results[0].to_dict()
    assert row["is_deleted"] is True

    await close_lance()
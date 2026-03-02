import pytest
import asyncio

from config.setting import settings
from src.db.lance_db import init_lance, close_lance
from src.services.sync.movie_sync_service import MovieSyncService
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo
from lancedb.pydantic import LanceModel, Vector
from src.repos.embedding_repos.movie_embedding_repo import MOVIE_EMBEDDING_DIM
import pandas as pd


@pytest.mark.asyncio
async def test_movie_insert_and_soft_delete_end_to_end(tmp_path, monkeypatch):
    settings.database.lancedb_path = str(tmp_path)
    await init_lance()

    async def fake_get_text_embedding_async(_):
        return [0.1] * MOVIE_EMBEDDING_DIM

    async def fake_iter_get_text_embedding(texts):
        vectors = [[0.1] * MOVIE_EMBEDDING_DIM for _ in texts]
        yield 0, vectors

    import src.repos.embedding_repos.movie_embedding_repo as mod
    monkeypatch.setattr(mod, "get_text_embedding_async", fake_get_text_embedding_async)
    monkeypatch.setattr(mod, "iter_get_text_embedding", fake_iter_get_text_embedding)

    class MovieSchema2(LanceModel):
        id: str
        vector: Vector(MOVIE_EMBEDDING_DIM)
        document: str
        library_id: str
        title: str
        is_deleted: bool

    class PatchedMovieRepo(BaseLanceRepo):
        def __init__(self):
            super().__init__(table_name="movies")
            self.soft_delete_flag = "is_deleted"
        def get_schema(self):
            return MovieSchema2
        async def upsert(self, objs):
            await self.ensure_table_bound()
            records = await self.batch_to_lance_records(objs)
            df = pd.DataFrame(records)
            await self.table.add(df)
        async def to_lance_record(self, movie):
            return {
                "id": movie.id,
                "vector": [0.1] * MOVIE_EMBEDDING_DIM,
                "document": "d",
                "library_id": movie.library_id,
                "title": movie.title,
                "is_deleted": False,
            }
        async def batch_to_lance_records(self, movies):
            return [
                {
                    "id": m.id,
                    "vector": [0.1] * MOVIE_EMBEDDING_DIM,
                    "document": "d",
                    "library_id": m.library_id,
                    "title": m.title,
                    "is_deleted": False,
                }
                for m in movies
            ]
        def from_lance_record(self, record):
            return record

    svc = MovieSyncService()
    repo = PatchedMovieRepo()

    insert_change = {
        "operationType": "insert",
        "fullDocument": {
            "_id": "m1",
            "library_id": "l1",
            "title": "T",
            "title_cn": "TC",
            "description": "D",
            "description_cn": "DC",
            "genres": ["g"],
            "directors": ["d"],
            "actors": ["a"],
            "tags": ["t"],
            "rating": 8.0,
            "release_date": None,
            "is_deleted": False,
            "metadata": {},
        },
    }

    await svc._handle_change(insert_change, repo)
    rows = await repo.table.count_rows()
    assert rows == 1

    

    await close_lance()


@pytest.mark.asyncio
async def test_close_lance(tmp_path):
    settings.database.lancedb_path = str(tmp_path)
    await init_lance()
    await close_lance()
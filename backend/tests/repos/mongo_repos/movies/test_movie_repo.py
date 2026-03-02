import pytest
from bson import ObjectId
from datetime import datetime, date, timezone

from src.repos.mongo_repos.movies.movie_repo import MovieRepo
from src.models import (
    MovieCreate,
    MovieInDB,
)

@pytest.fixture
def repo():
    return MovieRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_library_id_objectid_and_release_date_iso(repo: MovieRepo):
    create = MovieCreate(
        library_id="507f1f77bcf86cd799439011",
        title="MovieA",
        release_date=date(2024, 1, 2),
    )

    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # library_id 转 ObjectId
    assert isinstance(doc["library_id"], ObjectId)
    # release_date 序列化为 ISO 字符串
    assert doc["release_date"] == "2024-01-02"
    # 父类填充的通用字段
    assert doc["is_deleted"] is False
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_library_id_str_and_release_date_date(repo: MovieRepo):
    oid_lib = ObjectId("507f1f77bcf86cd799439011")
    docs = [
        {
            "_id": ObjectId(),
            "library_id": oid_lib,
            "title": "MovieB",
            "release_date": "2024-01-03",
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]

    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: MovieInDB = models[0]
    # _id 转 id，library_id 转字符串，release_date 反序列化为 date
    assert isinstance(m.id, str)
    assert m.library_id == str(oid_lib)
    assert isinstance(m.release_date, date)
    assert m.release_date == date(2024, 1, 3)
    assert m.title == "MovieB"
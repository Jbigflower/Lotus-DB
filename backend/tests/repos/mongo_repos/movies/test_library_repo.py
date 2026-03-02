import pytest
from bson import ObjectId
from datetime import datetime, timezone

from src.repos.mongo_repos.movies.library_repo import LibraryRepo
from src.models import (
    LibraryCreate,
    LibraryInDB,
    LibraryType,
)

@pytest.fixture
def repo():
    return LibraryRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_user_id_to_objectid(repo: LibraryRepo):
    create = LibraryCreate(
        user_id="507f1f77bcf86cd799439011",
        name="LibB",
        root_path="/data/libB",
        type=LibraryType.TV,
        description="",
        scan_interval=3600,
        auto_import=True,
        auto_import_scan_path="/scan",
        auto_import_supported_formats=["mp4"],
        is_public=True,
        is_active=False,
    )

    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # user_id 转 ObjectId
    assert isinstance(doc["user_id"], ObjectId)
    # 基础字段应存在
    assert doc["name"] == "LibB"
    assert doc["root_path"] == "/data/libB"
    assert doc["type"] == LibraryType.TV
    # 软删除与时间戳由父类填充
    assert doc["is_deleted"] is False
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_user_id_to_str_and_id_conversion(repo: LibraryRepo):
    oid = ObjectId("507f1f77bcf86cd799439011")
    docs = [
        {
            "_id": ObjectId(),
            "user_id": oid,
            "name": "LibC",
            "root_path": "/data/libC",
            "type": LibraryType.MOVIE,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]

    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: LibraryInDB = models[0]
    # _id 转 id，user_id 转字符串
    assert isinstance(m.id, str)
    assert m.user_id == str(oid)
    assert m.name == "LibC"
    assert m.root_path == "/data/libC"
    assert m.type == LibraryType.MOVIE
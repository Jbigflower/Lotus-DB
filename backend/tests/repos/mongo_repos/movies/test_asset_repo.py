import pytest
from bson import ObjectId
from datetime import datetime, timezone

from src.repos.mongo_repos.movies.asset_repo import AssetRepo
from src.models import (
    AssetCreate,
    AssetInDB,
    AssetType,
    AssetStoreType,
)

@pytest.fixture
def repo():
    return AssetRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_id_fields_to_objectid(repo: AssetRepo):
    create = AssetCreate(
        library_id="507f1f77bcf86cd799439011",
        movie_id="507f1f77bcf86cd799439012",
        type=AssetType.VIDEO,
        name="VideoA",
        path="/data/videoA.mp4",
        store_type=AssetStoreType.LOCAL,
        description="test video",
    )

    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # ID 字段转 ObjectId
    assert isinstance(doc["library_id"], ObjectId)
    assert isinstance(doc["movie_id"], ObjectId)
    # 基础字段应存在
    assert doc["type"] == AssetType.VIDEO
    assert doc["name"] == "VideoA"
    assert doc["path"] == "/data/videoA.mp4"
    # 软删除与时间戳由父类填充
    assert doc["is_deleted"] is False
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_id_fields_to_str_and_id_conversion(repo: AssetRepo):
    oid_lib = ObjectId("507f1f77bcf86cd799439011")
    oid_mov = ObjectId("507f1f77bcf86cd799439012")
    docs = [
        {
            "_id": ObjectId(),
            "library_id": oid_lib,
            "movie_id": oid_mov,
            "type": AssetType.SUBTITLE,
            "name": "SubA",
            "path": "/data/subA.srt",
            "store_type": AssetStoreType.LOCAL,
            "is_deleted": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]

    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: AssetInDB = models[0]
    # _id 转 id 字符串，library_id/movie_id 转字符串
    assert isinstance(m.id, str)
    assert m.library_id == str(oid_lib)
    assert m.movie_id == str(oid_mov)
    assert m.type == AssetType.SUBTITLE
    assert m.name == "SubA"
    assert m.path == "/data/subA.srt"
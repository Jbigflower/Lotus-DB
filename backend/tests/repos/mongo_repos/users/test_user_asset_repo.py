import pytest
from datetime import datetime, timezone
from bson import ObjectId

from src.repos.mongo_repos.users.user_asset_repo import UserAssetRepo
from src.models import (
    UserAssetCreate,
    UserAssetInDB,
    UserAssetType,
    AssetStoreType,
)

@pytest.fixture
def repo():
    return UserAssetRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_movie_ids_to_objectid(repo: UserAssetRepo):
    create = UserAssetCreate(
        user_id="507f1f77bcf86cd799439010",
        movie_id="507f1f77bcf86cd799439011",
        type=UserAssetType.NOTE,
        name="NoteA",
        related_movie_ids=["507f1f77bcf86cd799439012", "507f1f77bcf86cd799439013"],
        tags=["tag1"],
        is_public=False,
        permissions=[],
        path="/notes/a.md",
        store_type=AssetStoreType.LOCAL,
        content="hello",
    )
    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # movie_id 与 related_movie_ids 转 ObjectId
    assert isinstance(doc["movie_id"], ObjectId)
    assert all(isinstance(x, ObjectId) for x in doc["related_movie_ids"])
    # user_id 转 ObjectId
    assert isinstance(doc["user_id"], ObjectId)
    # 软删除与时间戳由父类填充
    assert doc["is_deleted"] is False
    assert doc["deleted_at"] is None
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_movie_ids_to_str(repo: UserAssetRepo):
    oid_mov = ObjectId("507f1f77bcf86cd799439011")
    oid_user = ObjectId("507f1f77bcf86cd799439010")
    docs = [
        {
            "_id": ObjectId(),
            "user_id": oid_user,
            "movie_id": oid_mov,
            "related_movie_ids": [ObjectId(), ObjectId()],
            "type": UserAssetType.SCREENSHOT,
            "name": "ShotA",
            "tags": [],
            "is_public": True,
            "permissions": [],
            "path": "/shots/a.png",
            "store_type": AssetStoreType.LOCAL,
            "is_deleted": False,
            "deleted_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]
    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: UserAssetInDB = models[0]
    assert isinstance(m.id, str)
    assert m.user_id == str(oid_user)
    assert m.movie_id == str(oid_mov)
    assert all(isinstance(x, str) for x in m.related_movie_ids)
    assert m.type == UserAssetType.SCREENSHOT
    assert m.name == "ShotA"

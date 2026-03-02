import pytest
from datetime import datetime, timezone
from bson import ObjectId

from src.repos.mongo_repos.users.watch_history_repo import WatchHistoryRepo
from src.models import WatchHistoryCreate, WatchHistoryInDB, WatchType

@pytest.fixture
def repo():
    return WatchHistoryRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_ids_to_objectid(repo: WatchHistoryRepo):
    create = WatchHistoryCreate(
        user_id="507f1f77bcf86cd799439011",
        asset_id="507f1f77bcf86cd799439012",
        movie_id="507f1f77bcf86cd799439013",
        type=WatchType.Official,
        last_position=120,
        total_duration=3600,
        subtitle_enabled=True,
        playback_rate=1.25,
        watch_count=2,
        total_watch_time=240,
        device_info={"os": "macOS"},
    )
    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # 三个 ID 转 ObjectId
    assert isinstance(doc["user_id"], ObjectId)
    assert isinstance(doc["asset_id"], ObjectId)
    assert isinstance(doc["movie_id"], ObjectId)
    # 软删除与时间戳由父类填充
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_ids_to_str(repo: WatchHistoryRepo):
    oid_user = ObjectId("507f1f77bcf86cd799439011")
    oid_asset = ObjectId("507f1f77bcf86cd799439012")
    oid_movie = ObjectId("507f1f77bcf86cd799439013")
    docs = [
        {
            "_id": ObjectId(),
            "user_id": oid_user,
            "asset_id": oid_asset,
            "movie_id": oid_movie,
            "type": WatchType.Community,
            "last_position": 30,
            "total_duration": 300,
            "subtitle_enabled": False,
            "playback_rate": 1.0,
            "watch_count": 1,
            "total_watch_time": 30,
            "device_info": {"os": "linux"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]
    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: WatchHistoryInDB = models[0]
    assert isinstance(m.id, str)
    assert m.user_id == str(oid_user)
    assert m.asset_id == str(oid_asset)
    assert m.movie_id == str(oid_movie)
    assert m.type == WatchType.Community
    assert m.last_position == 30
    assert m.total_duration == 300
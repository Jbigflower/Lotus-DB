import pytest
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from bson import ObjectId

from src.logic import WatchHistoryLogic
from src.models import WatchHistoryCreate, WatchHistoryInDB, WatchHistoryRead, WatchType, WatchHistoryPageResult
from src.core.exceptions import ConflictError

# --------- Fake Cache for WatchHistory ---------
class FakeWatchHistoryCache:
    def __init__(self):
        self.detail: Dict[str, Dict[str, Any]] = {}
        self.recent: Dict[str, List[Dict[str, Any]]] = {}
        self.search_pages: Dict[str, Dict[int, Dict[str, Any]]] = {}

    async def get_detail(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self.detail.get(item_id)

    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None) -> bool:
        oid = item.get("id")
        if oid:
            self.detail[oid] = item
            return True
        return False

    async def delete_search_cache_all(self) -> bool:
        self.search_pages.clear()
        return True

    async def clear_item_cache(self, item_id: str) -> bool:
        # BaseLogic.delete_by_id 会调用
        self.detail.pop(item_id, None)
        return True

    async def get_details_batch(self, item_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        # BaseLogic.get_by_ids 可能会调用
        return [self.detail.get(i) for i in item_ids]

    async def delete_details_batch(self, item_ids: List[str]) -> bool:
        # BaseLogic.deleted_by_ids 会调用
        for i in item_ids:
            self.detail.pop(i, None)
        return True

    # recent list helpers
    async def _update_recent_list(self, user_id: str, item: Dict[str, Any]) -> None:
        self.recent.setdefault(user_id, [])
        self.recent[user_id].insert(0, item)

    async def _get_recent_list(self, user_id: str, limit: int = 50):
        items = self.recent.get(user_id)
        if items is None:
            return None
        return [WatchHistoryRead(**it) for it in items[:limit]]

    async def _cache_recent_list(self, user_id: str, limit: int, items: List[WatchHistoryRead]) -> None:
        self.recent[user_id] = [it.model_dump() for it in items[:limit]]

    async def _delete_recent_list(self, user_id: str) -> None:
        self.recent.pop(user_id, None)

# --------- Fake Repo for WatchHistory ---------
class FakeWatchHistoryRepo:
    def __init__(self):
        self.store: Dict[str, WatchHistoryInDB] = {}
        self.last_query_filter: Optional[Dict[str, Any]] = None

    async def exists(self, filter_dict: Dict[str, Any], session=None) -> bool:
        # assert ObjectId type usage
        assert isinstance(filter_dict.get("user_id"), ObjectId)
        assert isinstance(filter_dict.get("asset_id"), ObjectId)
        # Simulate existence by scanning current store
        for wh in self.store.values():
            if ObjectId(wh.user_id) == filter_dict["user_id"] and ObjectId(wh.asset_id) == filter_dict["asset_id"]:
                return True
        return False

    async def insert_one(self, payload: WatchHistoryCreate, session=None) -> WatchHistoryInDB:
        _id = str(ObjectId())
        in_db = WatchHistoryInDB(
            id=_id,
            user_id=payload.user_id,
            asset_id=payload.asset_id,
            movie_id=payload.movie_id,
            type=payload.type,
            last_position=payload.last_position,
            total_duration=payload.total_duration,
            subtitle_enabled=payload.subtitle_enabled,
            subtitle_id=payload.subtitle_id,
            subtitle_sync_data=payload.subtitle_sync_data,
            playback_rate=payload.playback_rate,
            last_watched=payload.last_watched,
            watch_count=payload.watch_count,
            total_watch_time=payload.total_watch_time,
            device_info=payload.device_info,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.store[_id] = in_db
        return in_db

    async def update_by_id(self, watch_history_id: str, patch: Dict[str, Any], session=None) -> Optional[WatchHistoryInDB]:
        curr = self.store.get(watch_history_id)
        if not curr:
            return None
        data = curr.model_dump()
        data.update({k: v for k, v in patch.items() if v is not None})
        updated = WatchHistoryInDB(**data)
        updated.updated_at = datetime.now(timezone.utc)
        self.store[watch_history_id] = updated
        return updated

    async def find(self, filter_dict: Dict[str, Any], skip: int = 0, limit: int = 20, sort=None, session=None) -> List[WatchHistoryInDB]:
        self.last_query_filter = filter_dict
        # extremely simplified filtering for user_id and type
        def match(item: WatchHistoryInDB) -> bool:
            ok = True
            if "user_id" in filter_dict:
                ok = ok and ObjectId(item.user_id) == filter_dict["user_id"]
            if "type" in filter_dict:
                ok = ok and item.type.value == filter_dict["type"]
            if "watch_count" in filter_dict:
                cond = filter_dict["watch_count"]
                if "$gte" in cond:
                    ok = ok and item.watch_count >= cond["$gte"]
                if "$lte" in cond:
                    ok = ok and item.watch_count <= cond["$lte"]
            if "last_watched" in filter_dict:
                cond = filter_dict["last_watched"]
                if "$gte" in cond and item.last_watched:
                    ok = ok and item.last_watched >= cond["$gte"]
            return ok

        items = [v for v in self.store.values() if match(v)]
        # sort by last_watched desc when requested
        if sort and sort[0][0] == "last_watched":
            reverse = sort[0][1] == -1
            items.sort(key=lambda x: x.last_watched or datetime.min, reverse=reverse)
        return items[skip: skip + limit]

    async def count(self, filter_query: Dict[str, Any], session=None) -> int:
        return len(await self.find(filter_query, 0, 10**9, session=session))

    async def delete_by_id(self, watch_history_id: str, soft_delete: bool = True, session=None) -> int:
        return 1 if self.store.pop(watch_history_id, None) else 0

    async def delete_by_ids(self, ids: List[str], soft_delete: bool = True, session=None) -> int:
        cnt = 0
        for wid in ids:
            if self.store.pop(wid, None):
                cnt += 1
        return cnt

    async def aggregate(self, pipeline: List[Dict[str, Any]], session=None) -> List[Dict[str, Any]]:
        # very simplified aggregation for statistics
        items = list(self.store.values())
        total_movies = len(items)
        total_watch_time = sum(i.total_watch_time for i in items)
        total_watch_count = sum(i.watch_count for i in items)
        avg_progress = sum(
            (i.last_position / i.total_duration * 100) if i.total_duration else 0
            for i in items
        ) / (len(items) or 1)
        return [{
            "_id": None,
            "total_movies": total_movies,
            "total_watch_time": total_watch_time,
            "total_watch_count": total_watch_count,
            "avg_progress": avg_progress,
        }]

    async def delete_many(self, filter_dict: Dict[str, Any], session=None) -> int:
        keys_to_delete = []
        for key, item in self.store.items():
            match = True
            if "user_id" in filter_dict and ObjectId(item.user_id) != filter_dict["user_id"]:
                match = False
            if "movie_id" in filter_dict:
                cond = filter_dict["movie_id"]
                if isinstance(cond, dict) and "$in" in cond:
                    if ObjectId(item.movie_id) not in cond["$in"]:
                        match = False
                elif ObjectId(item.movie_id) != cond:
                    match = False
            if "asset_id" in filter_dict:
                cond = filter_dict["asset_id"]
                if isinstance(cond, dict) and "$in" in cond:
                    if ObjectId(item.asset_id) not in cond["$in"]:
                        match = False
                elif ObjectId(item.asset_id) != cond:
                    match = False
            if "type" in filter_dict and item.type.value != filter_dict["type"]:
                match = False
            
            if match:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self.store[key]
        return len(keys_to_delete)

# --------- Tests ---------
@pytest.mark.asyncio
async def test_create_watch_history_conflict():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    user_id = str(ObjectId())
    asset_id = str(ObjectId())

    # preset an existing record
    payload = WatchHistoryCreate(
        user_id=user_id,
        asset_id=asset_id,
        movie_id=str(ObjectId()),
        type=WatchType.Official,
        last_position=10,
        total_duration=100,
        subtitle_enabled=False,
        subtitle_id=None,
        subtitle_sync_data=None,
        playback_rate=1.0,
        last_watched=datetime.now(timezone.utc),
        watch_count=1,
        total_watch_time=10,
        device_info={},
    )
    # insert one to make exists True
    await logic.repo.insert_one(payload)

    with pytest.raises(ConflictError):
        await logic.create_watch_history(payload)

@pytest.mark.asyncio
async def test_create_watch_history_success_and_recent_cache():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    payload = WatchHistoryCreate(
        user_id=str(ObjectId()),
        asset_id=str(ObjectId()),
        movie_id=str(ObjectId()),
        type=WatchType.Community,
        last_position=5,
        total_duration=120,
        subtitle_enabled=True,
        subtitle_id=str(ObjectId()),
        subtitle_sync_data=3,
        playback_rate=1.25,
        last_watched=datetime.now(timezone.utc),
        watch_count=2,
        total_watch_time=50,
        device_info={"device": "mac"},
    )
    created = await logic.create_watch_history(payload)
    assert isinstance(created, WatchHistoryRead)
    # recent cache updated for the user
    recent = await logic.cache_repo._get_recent_list(payload.user_id, limit=10)
    assert recent is not None and len(recent) >= 1
    assert recent[0].asset_id == payload.asset_id

@pytest.mark.asyncio
async def test_get_recent_records_cache_hit():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    uid = str(ObjectId())
    # Pre-populate cache
    fake_items = [
        WatchHistoryRead(
            id=str(ObjectId()),
            user_id=uid,
            asset_id=str(ObjectId()),
            movie_id=str(ObjectId()),
            type=WatchType.Community,
            last_position=10,
            total_duration=100,
            last_watched=datetime.now(timezone.utc),
            watch_count=1,
            total_watch_time=10,
            device_info={},
            subtitle_enabled=False,
            subtitle_id=None,
            subtitle_sync_data=None,
            playback_rate=1.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    ]
    await logic.cache_repo._cache_recent_list(uid, 10, fake_items)

    # logic.get_recent_watch_histories should return from cache directly
    items = await logic.get_recent_watch_histories(uid, limit=10)
    assert len(items) == 1
    assert items[0].id == fake_items[0].id

@pytest.mark.asyncio
async def test_get_recent_records_fallback_db_and_cache_fill():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    uid = str(ObjectId())
    # cache miss -> repo.find should return items filtered by user_id ObjectId
    # pre-insert two records with the same user_id
    for _ in range(2):
        payload = WatchHistoryCreate(
            user_id=uid,
            asset_id=str(ObjectId()),
            movie_id=str(ObjectId()),
            type=WatchType.Community,
            last_position=10,
            total_duration=100,
            subtitle_enabled=False,
            subtitle_id=None,
            subtitle_sync_data=None,
            playback_rate=1.0,
            last_watched=datetime.now(timezone.utc),
            watch_count=1,
            total_watch_time=10,
            device_info={},
        )
        await logic.repo.insert_one(payload)

    items = await logic.get_recent_watch_histories(uid, limit=2)
    assert len(items) == 2
    # Verify order: newest first
    assert items[0].last_watched > items[1].last_watched

    # Verify cache fill: logic.cache_repo._cache_recent_list called
    # Since we use FakeWatchHistoryCache, we can inspect its store
    cached = await logic.cache_repo._get_recent_list(uid, limit=2)
    assert cached is not None
    assert len(cached) == 2

@pytest.mark.asyncio
async def test_delete_watch_history_clears_recent_cache():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    uid = str(ObjectId())
    payload = WatchHistoryCreate(
        user_id=uid,
        asset_id=str(ObjectId()),
        movie_id=str(ObjectId()),
        type=WatchType.Official,
        last_position=1,
        total_duration=10,
        subtitle_enabled=False,
        subtitle_id=None,
        subtitle_sync_data=None,
        playback_rate=1.0,
        last_watched=datetime.now(timezone.utc),
        watch_count=1,
        total_watch_time=1,
        device_info={},
    )
    created = await logic.repo.insert_one(payload)
    await logic.cache_repo._cache_recent_list(uid, 50, [WatchHistoryRead(**created.model_dump())])
    assert uid in logic.cache_repo.recent

    ok = await logic.delete_watch_history(created.id, uid)
    assert ok is True
    assert uid not in logic.cache_repo.recent

@pytest.mark.asyncio
async def test_get_user_watch_histories_pagination_and_objectid_filters():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    uid = str(ObjectId())
    # insert three records, 2 match type Official and user_id
    for t in (WatchType.Official, WatchType.Community, WatchType.Official):
        payload = WatchHistoryCreate(
            user_id=uid,
            asset_id=str(ObjectId()),
            movie_id=str(ObjectId()),
            type=t,
            last_position=10,
            total_duration=100,
            subtitle_enabled=False,
            subtitle_id=None,
            subtitle_sync_data=None,
            playback_rate=1.0,
            last_watched=datetime.now(timezone.utc),
            watch_count=1,
            total_watch_time=10,
            device_info={},
        )
        await logic.repo.insert_one(payload)

    page = await logic.get_user_watch_histories(
        user_id=uid,
        watch_type=WatchType.Official,
        page=1,
        size=10,
    )
    assert isinstance(page, WatchHistoryPageResult)
    assert page.total == 2
    # ensure filter used ObjectId
    assert isinstance(logic.repo.last_query_filter["user_id"], ObjectId)

@pytest.mark.asyncio
async def test_delete_by_filter():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    user_id = str(ObjectId())
    movie_id1 = str(ObjectId())
    movie_id2 = str(ObjectId())
    asset_id1 = str(ObjectId())
    
    # Create records
    await logic.create_watch_history(WatchHistoryCreate(
        user_id=user_id, asset_id=asset_id1, movie_id=movie_id1, type=WatchType.Official,
        last_position=0, total_duration=100,
        subtitle_enabled=False, subtitle_id=None, subtitle_sync_data=None, playback_rate=1.0,
        last_watched=datetime.now(timezone.utc), watch_count=1, total_watch_time=0, device_info={}
    ))
    await logic.create_watch_history(WatchHistoryCreate(
        user_id=user_id, asset_id=str(ObjectId()), movie_id=movie_id2, type=WatchType.Official,
        last_position=0, total_duration=100,
        subtitle_enabled=False, subtitle_id=None, subtitle_sync_data=None, playback_rate=1.0,
        last_watched=datetime.now(timezone.utc), watch_count=1, total_watch_time=0, device_info={}
    ))
    
    # Verify created
    assert len(logic.repo.store) == 2
    
    # Delete by movie_id
    deleted = await logic.delete_by_filter(movie_ids=[movie_id1])
    assert deleted == 1
    assert len(logic.repo.store) == 1
    
    # Verify remaining is movie_id2
    remaining = list(logic.repo.store.values())[0]
    assert ObjectId(remaining.movie_id) == ObjectId(movie_id2)
    
    # Create another one for asset deletion test
    asset_id3 = str(ObjectId())
    await logic.create_watch_history(WatchHistoryCreate(
        user_id=user_id, asset_id=asset_id3, movie_id=movie_id1, type=WatchType.Official,
        last_position=0, total_duration=100,
        subtitle_enabled=False, subtitle_id=None, subtitle_sync_data=None, playback_rate=1.0,
        last_watched=datetime.now(timezone.utc), watch_count=1, total_watch_time=0, device_info={}
    ))
    assert len(logic.repo.store) == 2
    
    # Delete by asset_id
    deleted = await logic.delete_by_filter(asset_ids=[asset_id3])
    assert deleted == 1
    assert len(logic.repo.store) == 1


@pytest.mark.asyncio
async def test_finished_filter_builds_expr():
    logic = WatchHistoryLogic()
    logic.repo = FakeWatchHistoryRepo()
    logic.cache_repo = FakeWatchHistoryCache()

    uid = str(ObjectId())
    # call finished=True
    await logic.get_user_watch_histories(user_id=uid, finished=True, page=1, size=10)
    f1 = logic.repo.last_query_filter
    assert "$expr" in f1 and "$or" not in f1
    # call finished=False
    await logic.get_user_watch_histories(user_id=uid, finished=False, page=1, size=10)
    f2 = logic.repo.last_query_filter
    assert "$or" in f2
    # ensure legacy field not used
    assert "progress_percentage" not in f1 and "progress_percentage" not in f2
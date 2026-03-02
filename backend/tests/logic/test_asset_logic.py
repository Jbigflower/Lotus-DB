import pytest
from typing import Any, Dict, List, Optional
from bson import ObjectId
from datetime import datetime, timezone

from src.logic.movies.asset_logic import MovieAssetLogic as AssetLogic
from src.models import AssetInDB, AssetRead, AssetCreate, AssetType, AssetStoreType, AssetPageResult
from src.routers.schemas import movie

# --------- Fake Cache for Asset ---------
class FakeAssetCache:
    def __init__(self):
        self.details: Dict[str, Dict[str, Any]] = {}
        self.search_pages: Dict[str, Dict[int, Dict[str, Any]]] = {}
        self.item_lists: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    async def get_detail(self, item_id: str):
        return self.details.get(item_id)

    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None) -> bool:
        if item.get("id"):
            self.details[item["id"]] = item
            return True
        return False

    async def delete_search_cache_all(self) -> bool:
        self.search_pages.clear()
        return True

    async def get_search_page(self, key: str, page: int) -> Optional[Dict[str, Any]]:
        return self.search_pages.get(key, {}).get(page)

    async def cache_search_page(self, key: str, page: int, payload: Dict[str, Any]) -> None:
        self.search_pages.setdefault(key, {})[page] = payload

    # list helpers used by logic.list_movie_assets
    async def _get_item_list(self, domain: str, item_id: str) -> Optional[List[Dict[str, Any]]]:
        return self.item_lists.get(domain, {}).get(item_id)

    async def _cache_item_list(self, domain: str, item_id: str, items: List[Dict[str, Any]]) -> None:
        self.item_lists.setdefault(domain, {})[item_id] = items

    async def delete_details_batch(self, ids: List[str]) -> None:
        for _id in ids:
            self.details.pop(_id, None)

    async def delete_item_list(self, domain: str, item_id: str) -> None:
        if domain in self.item_lists:
            self.item_lists[domain].pop(item_id, None)

# --------- Fake Repo for Asset ---------
class FakeAssetRepo:
    def __init__(self):
        self.store: Dict[str, AssetInDB] = {}
        self.last_filter: Optional[Dict[str, Any]] = None

    async def find(self, filter_dict: Dict[str, Any], skip: int = 0, limit: int = 20, sort: Optional[List[tuple]] = None, projection=None, session=None):
        self.last_filter = filter_dict
        # basic filtering for movie_id, type
        def match(item: AssetInDB):
            ok = True
            if "movie_id" in filter_dict:
                mv = filter_dict["movie_id"]
                if isinstance(mv, dict) and "$in" in mv:
                    ok = ok and ObjectId(item.movie_id) in mv["$in"]
                else:
                    ok = ok and ObjectId(item.movie_id) == mv
            if "type" in filter_dict:
                ok = ok and item.type.value == filter_dict["type"]
            if "metadata.size" in filter_dict:
                cond = filter_dict["metadata.size"]
                size = item.model_dump().get("metadata", {}).get("size", 0)
                if "$gte" in cond:
                    ok = ok and size >= cond["$gte"]
                if "$lte" in cond:
                    ok = ok and size <= cond["$lte"]
            return ok

        items = [v for v in self.store.values() if match(v)]
        return items[skip: skip + limit]

    async def count(self, filter_dict: Dict[str, Any], session=None) -> int:
        return len(await self.find(filter_dict, 0, 10**9, session=session))

# --------- Helpers ---------
def make_asset(library_id: str, movie_id: str, name: str, atype: AssetType = AssetType.VIDEO) -> AssetInDB:
    return AssetInDB(
        id=str(ObjectId()),
        library_id=library_id,
        movie_id=movie_id,
        type=atype,
        name=name,
        path="/tmp/file",
        store_type=AssetStoreType.LOCAL,
        actual_path=None,
        description="",
        metadata=None,
        is_deleted=False,
        deleted_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

# --------- Tests ---------
@pytest.mark.asyncio
async def test_list_movie_assets_cache_hit():
    logic = AssetLogic()
    logic.repo = FakeAssetRepo()
    logic.cache_repo = FakeAssetCache()

    movie_id = str(ObjectId())
    asset = make_asset(str(ObjectId()), movie_id, "A1")
    # cache hit with dicts
    await logic.cache_repo._cache_item_list("movie", movie_id, [asset.model_dump()])

    res = await logic.list_movies_assets([movie_id])
    res = res[movie_id]
    assert len(res) == 1 and isinstance(res[0], AssetRead)
    assert res[0].id == asset.id

@pytest.mark.asyncio
async def test_list_movie_assets_db_and_cache_fill():
    logic = AssetLogic()
    logic.repo = FakeAssetRepo()
    logic.cache_repo = FakeAssetCache()

    movie_id = str(ObjectId())
    a1 = make_asset(str(ObjectId()), movie_id, "A1")
    a2 = make_asset(str(ObjectId()), movie_id, "A2")
    logic.repo.store[a1.id] = a1
    logic.repo.store[a2.id] = a2

    res = await logic.list_movies_assets([movie_id])
    res = res[movie_id]
    assert len(res) == 2
    # list cache filled
    cached = await logic.cache_repo._get_item_list("movie", movie_id)
    assert cached is not None and len(cached) == 2

@pytest.mark.asyncio
async def test_search_assets_filters_and_objectid_usage():
    logic = AssetLogic()
    logic.repo = FakeAssetRepo()
    logic.cache_repo = FakeAssetCache()

    mv = str(ObjectId())
    logic.repo.store["x1"] = make_asset(str(ObjectId()), mv, "X1", AssetType.VIDEO)
    logic.repo.store["x2"] = make_asset(str(ObjectId()), mv, "X2", AssetType.SUBTITLE)

    page = await logic.search_assets(
        query=None,
        movie_id=mv,
        asset_type="video",
        min_size=None,
        max_size=None,
        min_duration=None,
        max_duration=None,
        addition_filter=None,
        page=1,
        size=10,
        sort=None,
        projection=None,
    )
    assert isinstance(page, AssetPageResult)
    assert page.total == 1
    # movie_id filter is ObjectId typed
    assert isinstance(logic.repo.last_filter["movie_id"], ObjectId)
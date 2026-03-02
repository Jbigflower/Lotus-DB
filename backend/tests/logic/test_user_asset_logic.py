import pytest
from typing import Any, Dict, Optional, List, Tuple
from bson import ObjectId
from datetime import datetime, timezone

from src.logic import UserAssetLogic
from src.models import UserAssetCreate, UserAssetInDB, UserAssetRead, UserAssetType, UserAssetPageResult, PartialPageResult, AssetStoreType

# --------- Fake Cache ---------
class FakeUserAssetCache:
    def __init__(self):
        self.details: Dict[str, Dict[str, Any]] = {}

    async def get_detail(self, item_id: str): return self.details.get(item_id)
    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None):
        if item.get("id"): self.details[item["id"]] = item; return True
        return False
    async def delete_search_cache_all(self): return True

# --------- Fake Repo ---------
class FakeUserAssetRepo:
    MAX_FIND_LIMIT = 1000

    def __init__(self):
        self.store: Dict[str, UserAssetInDB] = {}
        self.last_filter: Optional[Dict[str, Any]] = None

    async def find(self, filter_dict: Dict[str, Any], skip: int = 0, limit: int = 20, sort: Optional[List[Tuple[str, int]]] = None, projection: Optional[Dict[str, int]] = None, session=None):
        self.last_filter = filter_dict
        def match(item: UserAssetInDB):
            ok = True
            if "user_id" in filter_dict:
                ok = ok and ObjectId(item.user_id) == filter_dict["user_id"]
            if "movie_id" in filter_dict:
                mv = filter_dict["movie_id"]
                if isinstance(mv, dict) and "$in" in mv:
                    ok = ok and ObjectId(item.movie_id) in mv["$in"]
                else:
                    ok = ok and ObjectId(item.movie_id) == mv
            if "type" in filter_dict:
                if isinstance(filter_dict["type"], dict) and "$in" in filter_dict["type"]:
                    ok = ok and item.type.value in filter_dict["type"]["$in"]
                else:
                    ok = ok and item.type.value == filter_dict["type"]
            if "tags" in filter_dict and "$in" in filter_dict["tags"]:
                ok = ok and any(t in item.tags for t in filter_dict["tags"]["$in"])
            if "is_public" in filter_dict:
                ok = ok and item.is_public == filter_dict["is_public"]
            return ok
        items = [v for v in self.store.values() if match(v)]
        if projection is not None:
            # simulate partial docs
            proj_items = []
            for it in items[skip: skip+limit]:
                doc = {k: it.model_dump().get(k) for k in projection.keys()}
                proj_items.append(doc)
            return proj_items
        return items[skip: skip + limit]

    async def count(self, filter_dict: Dict[str, Any], session=None):
        items = await self.find(filter_dict, 0, 10**9, projection=None, session=session)
        return len(items)

# --------- Helpers ---------
def make_user_asset(uid: str, mid: str, name: str, typ: UserAssetType, is_public: bool, tags: List[str]) -> UserAssetInDB:
    return UserAssetInDB(
        id=str(ObjectId()),
        user_id=uid,
        movie_id=mid,
        type=typ,
        name=name,
        related_movie_ids=[],
        tags=tags,
        is_public=is_public,
        permissions=[],
        path="/tmp/asset",
        store_type=AssetStoreType.LOCAL,
        actual_path=None,
        content=None,
        metadata=None,
        is_deleted=False,
        deleted_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        movie_info=None,
        require_allocate=False,
    )

# --------- Tests ---------
@pytest.mark.asyncio
async def test_list_assets_projection_partial_result_and_objectids():
    logic = UserAssetLogic()
    logic.repo = FakeUserAssetRepo()
    logic.cache_repo = FakeUserAssetCache()

    uid = str(ObjectId())
    mid = str(ObjectId())
    a1 = make_user_asset(uid, mid, "Note1", UserAssetType.NOTE, True, ["a"])
    a2 = make_user_asset(uid, mid, "Clip1", UserAssetType.CLIP, False, ["b"])
    logic.repo.store[a1.id] = a1
    logic.repo.store[a2.id] = a2

    page = await logic.list_assets(
        query=None,
        user_id=uid,
        movie_ids=[mid],
        asset_type=[UserAssetType.NOTE, None],
        tags=None,
        is_public=None,
        page=1,
        size=10,
        sort=None,
        projection={"id": 1, "name": 1},
    )
    assert isinstance(page, PartialPageResult)
    assert page.total == 1
    assert isinstance(logic.repo.last_filter["user_id"], ObjectId)
    assert isinstance(logic.repo.last_filter["movie_id"], ObjectId)

@pytest.mark.asyncio
async def test_list_assets_full_result_with_type_in_filter():
    logic = UserAssetLogic()
    logic.repo = FakeUserAssetRepo()
    logic.cache_repo = FakeUserAssetCache()

    uid = str(ObjectId())
    mid = str(ObjectId())
    logic.repo.store["n1"] = make_user_asset(uid, mid, "Note1", UserAssetType.NOTE, True, ["a"])
    logic.repo.store["n2"] = make_user_asset(uid, mid, "Note2", UserAssetType.NOTE, False, ["b"])
    logic.repo.store["c1"] = make_user_asset(uid, mid, "Clip1", UserAssetType.CLIP, True, ["c"])

    page = await logic.list_assets(
        query=None,
        user_id=uid,
        movie_ids=[mid],
        asset_type=[UserAssetType.NOTE, UserAssetType.CLIP],
        tags=["c"],
        is_public=True,
        page=1,
        size=10,
        sort=None,
        projection=None,
    )
    assert isinstance(page, UserAssetPageResult)
    assert page.total == 1
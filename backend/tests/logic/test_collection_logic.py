import pytest
from typing import Any, Dict, Optional
from bson import ObjectId
from datetime import datetime, timezone

from src.logic.users.collection_logic import CollectionLogic
from src.models import CustomListCreate, CustomListUpdate, CustomListInDB, CustomListRead, CustomListType
from src.core.exceptions import ConflictError, ValidationError

# --------- Fake Cache ---------
class FakeCollectionCache:
    def __init__(self):
        self.details = {}

    async def get_detail(self, item_id: str): return self.details.get(item_id)
    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None):
        if item.get("id"): self.details[item["id"]] = item; return True
        return False
    async def delete_search_cache_all(self): return True

# --------- Fake Repo ---------
class FakeCollectionRepo:
    def __init__(self):
        self.store: Dict[str, CustomListInDB] = {}

    async def exists(self, filter_dict: Dict[str, Any], session=None):
        return any(v.name == filter_dict.get("name") for v in self.store.values())

    async def find_by_id(self, doc_id: str, session=None): return self.store.get(doc_id)

    async def insert_one(self, payload: CustomListCreate, session=None) -> CustomListInDB:
        _id = str(ObjectId())
        in_db = CustomListInDB(
            id=_id,
            user_id=payload.user_id,
            name=payload.name,
            type=payload.type,
            description=payload.description,
            is_public=payload.is_public,
            movies=payload.movies,
            is_deleted=False,
            deleted_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.store[_id] = in_db
        return in_db

    async def update_by_id(self, doc_id: str, patch: Dict[str, Any], session=None):
        curr = self.store.get(doc_id)
        if not curr:
            return None
        data = curr.model_dump()
        data.update(patch)
        upd = CustomListInDB(**data)
        self.store[doc_id] = upd
        return upd

# --------- Tests ---------
@pytest.mark.asyncio
async def test_create_collection_reject_reserved_types():
    logic = CollectionLogic()
    logic.repo = FakeCollectionRepo()
    logic.cache_repo = FakeCollectionCache()

    uid = str(ObjectId())
    for t in (CustomListType.FAVORITE, CustomListType.WATCHLIST):
        with pytest.raises(ValidationError):
            # 有 包装器 进行异常类型转换
            await logic.create_collection(CustomListCreate(
                name="Default",
                type=t,
                description="",
                is_public=False,
                movies=[],
                user_id=uid,
            ))

@pytest.mark.asyncio
async def test_update_collection_name_conflict():
    logic = CollectionLogic()
    logic.repo = FakeCollectionRepo()
    logic.cache_repo = FakeCollectionCache()

    created = await logic.repo.insert_one(CustomListCreate(
        name="A",
        type=CustomListType.CUSTOMLIST,
        description="",
        is_public=False,
        movies=[],
        user_id=str(ObjectId()),
    ))
    await logic.repo.insert_one(CustomListCreate(
        name="dup",
        type=CustomListType.CUSTOMLIST,
        description="",
        is_public=False,
        movies=[],
        user_id=str(ObjectId()),
    ))

    with pytest.raises(ConflictError):
        await logic.update_collection(created.id, CustomListUpdate(name="dup"))
import pytest
from typing import Any, Dict, Optional, List
from bson import ObjectId
from datetime import datetime, timezone

from src.logic.movies.library_logic import LibraryLogic
from src.models import LibraryCreate, LibraryUpdate, LibraryInDB, LibraryRead, LibraryPageResult, LibraryType, UserRole
from src.core.exceptions import ConflictError, ValidationError

# --------- Fake Cache ---------
class FakeLibraryCache:
    def __init__(self):
        self.details: Dict[str, Dict[str, Any]] = {}
        self.search_pages: Dict[str, Dict[int, Dict[str, Any]]] = {}

    async def get_detail(self, item_id: str): return self.details.get(item_id)
    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None): 
        if item.get("id"): self.details[item["id"]] = item; return True
        return False
    async def delete_search_cache_all(self): self.search_pages.clear(); return True
    async def get_search_page(self, key: str, page: int): return self.search_pages.get(key, {}).get(page)
    async def cache_search_page(self, key: str, page: int, payload: Dict[str, Any]): self.search_pages.setdefault(key, {})[page] = payload

# --------- Fake Repo ---------
class FakeLibraryRepo:
    def __init__(self):
        self.store: Dict[str, LibraryInDB] = {}
        self.exists_response: bool = False
        self.last_filter: Optional[Dict[str, Any]] = None

    async def exists(self, filter_dict: Dict[str, Any], session=None) -> bool:
        # name duplicates check
        self.exists_response = any(v.name == filter_dict.get("name") for v in self.store.values())
        return self.exists_response

    async def find_by_id(self, doc_id: str, session=None) -> Optional[LibraryInDB]:
        return self.store.get(doc_id)

    async def insert_one(self, payload: LibraryCreate, session=None) -> LibraryInDB:
        _id = str(ObjectId())
        in_db = LibraryInDB(
            id=_id,
            user_id=payload.user_id,
            name=payload.name,
            root_path=payload.root_path or "/data",
            type=payload.type,
            description=payload.description,
            scan_interval=payload.scan_interval,
            auto_import=payload.auto_import,
            auto_import_scan_path=payload.auto_import_scan_path,
            auto_import_supported_formats=payload.auto_import_supported_formats,
            is_public=payload.is_public,
            is_active=payload.is_active,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_deleted=False,
            deleted_at=None,
        )
        self.store[_id] = in_db
        return in_db

    async def update_by_id(self, doc_id: str, patch: Dict[str, Any], session=None) -> Optional[LibraryInDB]:
        curr = self.store.get(doc_id)
        if not curr:
            return None
        data = curr.model_dump()
        data.update(patch)
        upd = LibraryInDB(**data)
        self.store[doc_id] = upd
        return upd

    async def find(self, filter_dict: Dict[str, Any], skip: int = 0, limit: int = 20, session=None):
        self.last_filter = filter_dict
        # very simplified filter
        def match(item: LibraryInDB):
            ok = True
            if "user_id" in filter_dict:
                ok = ok and ObjectId(item.user_id) == filter_dict["user_id"]
            if "is_active" in filter_dict:
                ok = ok and item.is_active == filter_dict["is_active"]
            if "is_deleted" in filter_dict:
                ok = ok and item.is_deleted == filter_dict["is_deleted"]
            if "type" in filter_dict:
                ok = ok and item.type.value == filter_dict["type"]
            return ok
        items = [v for v in self.store.values() if match(v)]
        return items[skip: skip + limit]

    async def count(self, filter_dict: Dict[str, Any], session=None):
        return len(await self.find(filter_dict, 0, 10**9, session=session))

# --------- Tests ---------
@pytest.mark.asyncio
async def test_create_library_conflict_name():
    logic = LibraryLogic()
    logic.repo = FakeLibraryRepo()
    logic.cache_repo = FakeLibraryCache()

    payload = LibraryCreate(
        user_id=str(ObjectId()),
        name="MyLib",
        root_path="/data",
        type=LibraryType.MOVIE,
        description="d",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=False,
        is_active=True,
    )
    # preset duplicate
    await logic.repo.insert_one(payload)
    with pytest.raises(ConflictError):
        await logic.create_library(payload)

@pytest.mark.asyncio
async def test_update_library_name_conflict():
    logic = LibraryLogic()
    logic.repo = FakeLibraryRepo()
    logic.cache_repo = FakeLibraryCache()

    created = await logic.repo.insert_one(LibraryCreate(
        user_id=str(ObjectId()),
        name="L1",
        root_path="/data",
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=False,
        is_active=True,
    ))
    # add another same-name lib to trigger conflict
    await logic.repo.insert_one(LibraryCreate(
        user_id=str(ObjectId()),
        name="dup",
        root_path="/data2",
        type=LibraryType.TV,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=False,
        is_active=True,
    ))

    # trying to update to "dup"
    with pytest.raises(ConflictError):
        await logic.update_library(created.id, LibraryUpdate(name="dup"))

@pytest.mark.asyncio
async def test_update_library_activity_no_change_returns_same():
    logic = LibraryLogic()
    logic.repo = FakeLibraryRepo()
    logic.cache_repo = FakeLibraryCache()

    lib = await logic.repo.insert_one(LibraryCreate(
        user_id=str(ObjectId()),
        name="L2",
        root_path="/d",
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=False,
        is_active=False,
    ))
    got = await logic.update_library_activity(lib.id, is_active=False)
    assert got.id == lib.id and got.is_active is False

@pytest.mark.asyncio
async def test_list_libraries_user_role_filters_objectid():
    logic = LibraryLogic()
    logic.repo = FakeLibraryRepo()
    logic.cache_repo = FakeLibraryCache()

    uid = str(ObjectId())
    await logic.repo.insert_one(LibraryCreate(
        user_id=uid,
        name="MyLib",
        root_path="/data",
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=False,
        is_active=True,
    ))

    page = await logic.list_libraries(
        role=UserRole.USER,
        user_id=uid,
        only_me=True,
        page=1,
        page_size=10,
        session=None,
    )
    assert isinstance(page, LibraryPageResult)
    # ensure filter used ObjectId for user_id
    assert isinstance(logic.repo.last_filter.get("user_id"), ObjectId)
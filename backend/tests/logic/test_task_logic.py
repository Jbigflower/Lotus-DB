import pytest
from typing import Any, Dict, Optional
from bson import ObjectId
from datetime import datetime, timezone

from src.logic import TaskLogic  # if path differs, adjust accordingly
from src.models import TaskInDB, TaskRead, TaskCreate, TaskUpdate, TaskStatus, TaskType, TaskSubType, TaskPriority, ProgressInfo

from src.core.exceptions import ValidationError, NotFoundError

# NOTE: Depending on your repo structure, TaskLogic may be at src/logic/task/task_logic.py
# If import path above fails, use: from src.logic.task.task_logic import TaskLogic

# --------- Fake Cache ---------
class FakeTaskCache:
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
class FakeTaskRepo:
    def __init__(self):
        self.store: Dict[str, TaskInDB] = {}

    async def find_by_id(self, tid: str, session=None):
        return self.store.get(tid)

    async def insert_one(self, payload: TaskCreate, session=None):
        _id = str(ObjectId())
        in_db = TaskInDB(
            id=_id,
            name="task",
            description="",
            task_type=payload.task_type,
            sub_type=payload.sub_type,
            priority=payload.priority,
            parameters=payload.parameters,
            status=payload.status,
            progress=ProgressInfo(),
            result={},
            user_id=payload.user_id,
            parent_task_id=None,
            error_message="",
            error_details={},
            scheduled_at=None,
            retry_count=0,
            max_retries=payload.max_retries,
            timeout_seconds=payload.timeout_seconds,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            retry_at=None,
            completed_at=None,
            updated_at=datetime.now(timezone.utc),
        )
        self.store[_id] = in_db
        return in_db

    async def update_by_id(self, tid: str, patch: Dict[str, Any], session=None):
        curr = self.store.get(tid)
        if not curr:
            return None
        data = curr.model_dump()
        # convert status string to TaskStatus when present
        if "status" in patch and isinstance(patch["status"], str):
            patch["status"] = TaskStatus(patch["status"])
        data.update(patch)
        upd = TaskInDB(**data)
        self.store[tid] = upd
        return upd

    async def find(self, filter_dict: Dict[str, Any], skip: int = 0, limit: int = 20, session=None):
        def match(item: TaskInDB):
            ok = True
            if "status" in filter_dict:
                ok = ok and item.status.value == filter_dict["status"]
            if "user_id" in filter_dict:
                ok = ok and (item.user_id == filter_dict["user_id"])
            if "type" in filter_dict:
                ok = ok and item.task_type.value == filter_dict["type"]
            if "priority" in filter_dict:
                ok = ok and item.priority.value == filter_dict["priority"]
            if "sub_type" in filter_dict:
                ok = ok and item.sub_type.value == filter_dict["sub_type"]
            return ok
        items = [v for v in self.store.values() if match(v)]
        return items[skip: skip + limit]

    async def count(self, filter_dict: Dict[str, Any], session=None):
        return len(await self.find(filter_dict, 0, 10**9, session=session))

# --------- Tests ---------
@pytest.mark.asyncio
async def test_start_cancel_complete_task_flow():
    # Prefer explicit import from src.logic.task.task_logic if path above doesn't work
    logic = TaskLogic()
    logic.repo = FakeTaskRepo()
    logic.cache_repo = FakeTaskCache()

    created = await logic.create_task(TaskCreate(
        name="T1",
        description="",
        task_type=TaskType.OTHER,
        sub_type=TaskSubType.REFRESH_COLLECTION_CACHE,
        priority=TaskPriority.NORMAL,
        parameters={},
        status=TaskStatus.PENDING,
        user_id=str(ObjectId()),
        max_retries=3,
        timeout_seconds=3600,
        scheduled_at=None,
    ))
    # start task
    started = await logic.start_task(created.id)
    assert started.status == TaskStatus.RUNNING
    assert started.started_at is not None

    # cancel running task -> paused then cancelled
    cancelled = await logic.cancel_task(created.id)
    assert cancelled.status == TaskStatus.CANCELLED
    assert cancelled.completed_at is not None

    # reopen a new running task to complete it
    created2 = await logic.create_task(TaskCreate(
        name="T2",
        description="",
        task_type=TaskType.OTHER,
        sub_type=TaskSubType.REFRESH_COLLECTION_CACHE,
        priority=TaskPriority.NORMAL,
        parameters={},
        status=TaskStatus.PENDING,
        user_id=str(ObjectId()),
        max_retries=3,
        timeout_seconds=3600,
        scheduled_at=None,
    ))
    _ = await logic.start_task(created2.id)
    completed = await logic.complete_task(created2.id, result={"ok": True})
    assert completed.status == TaskStatus.COMPLETED
    assert completed.result.get("ok") is True
    assert completed.completed_at is not None

@pytest.mark.asyncio
async def test_search_tasks_filters_and_cache():
    logic = TaskLogic()
    logic.repo = FakeTaskRepo()
    logic.cache_repo = FakeTaskCache()

    t1 = await logic.create_task(TaskCreate(
        name="A",
        description="",
        task_type=TaskType.IMPORT,
        sub_type=TaskSubType.MOVIE_IMPORT,
        priority=TaskPriority.HIGH,
        parameters={},
        status=TaskStatus.PENDING,
        user_id=str(ObjectId()),
        max_retries=3,
        timeout_seconds=3600,
        scheduled_at=None,
    ))
    t2 = await logic.create_task(TaskCreate(
        name="B",
        description="",
        task_type=TaskType.OTHER,
        sub_type=TaskSubType.REFRESH_COLLECTION_CACHE,
        priority=TaskPriority.NORMAL,
        parameters={},
        status=TaskStatus.RUNNING,
        user_id=str(ObjectId()),
        max_retries=3,
        timeout_seconds=3600,
        scheduled_at=None,
    ))

    page = await logic.search_tasks(
        query=None,
        task_type=TaskType.OTHER,
        sub_type=None,
        status=None,
        priority=None,
        user_id=None,
        page=1,
        page_size=20,
    )
    assert len(page.items) == 1 and page.items[0].id == t2.id
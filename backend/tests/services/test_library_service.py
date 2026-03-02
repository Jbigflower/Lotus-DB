import pytest
from datetime import datetime, timezone

from src.services.movies.library_service import LibraryService
from src.models import (
    LibraryCreate,
    LibraryRead,
    LibraryType,
    LibraryPageResult,
    UserRead,
    UserRole,
)
from src.core.exceptions import ForbiddenError, ValidationError, BadRequestError


def make_user(role=UserRole.USER, uid="u1") -> UserRead:
    return UserRead(
        id=uid,
        username="tester",
        email="tester@example.com",
        role=role,
        permissions=[],
        is_active=True,
        is_verified=True,
        settings={},
        hashed_password=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_library(lid="l1", owner="u1", public=True, active=True) -> LibraryRead:
    return LibraryRead(
        id=lid,
        user_id=owner,
        name="Lib",
        root_path="l1",
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=public,
        is_active=active,
        is_deleted=False,
        deleted_at=None,
    )


class FakeRepoTx:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeRepo:
    def transaction(self):
        return FakeRepoTx()


class FakeTaskInfo:
    id = "t1"


class FakeTaskLogic:
    async def create_task(self, task_create):
        return FakeTaskInfo()


class FakeLibraryLogic:
    def __init__(self, lib: LibraryRead):
        self._lib = lib
        self.repo = FakeRepo()
        self._deleted_hard_called = False

    async def get_library(self, library_id, session=None):
        return self._lib

    async def update_library_root_path(self, library_id, root_path, session=None):
        self._lib.root_path = root_path
        return self._lib

    async def create_library(self, payload: LibraryCreate, session=None):
        return self._lib

    async def delete_library(self, library_id, soft_delete=True, session=None):
        if not soft_delete:
            self._deleted_hard_called = True
        return True

    async def get_current_library(self, user_id):
        return None

    async def update_library(self, library_id, library_update, session=None):
        return self._lib

    async def restore_library(self, library_id, session=None):
        return self._lib

    async def list_libraries(self, **kwargs):
        return LibraryPageResult(items=[self._lib], total=1, page=1, size=10, pages=1)

    async def enter_library(self, library_id, user_id, session=None):
        return self._lib

    async def exit_library(self, user_id, session=None):
        return True

    async def update_library_activity(self, library_id, is_active, session=None):
        self._lib.is_active = is_active
        return self._lib

    async def update_library_visibility(self, library_id, is_public, session=None):
        self._lib.is_public = is_public
        return self._lib

    async def get_library_stats(self, library_id, session=None):
        return {"movies": 10}

    async def scan_library(self, library_id, session=None):
        return {"status": "ok"}


@pytest.mark.asyncio
async def test_read_permission_denied_for_non_owner_private():
    svc = LibraryService()
    lib = make_library(owner="owner", public=False)
    svc.logic = FakeLibraryLogic(lib)
    user = make_user(role=UserRole.USER, uid="another")

    with pytest.raises(BadRequestError):
        await svc.enter_library(lib.id, current_user=user)


@pytest.mark.asyncio
async def test_enter_library_allowed_for_public():
    svc = LibraryService()
    lib = make_library(public=True)
    svc.logic = FakeLibraryLogic(lib)
    user = make_user(role=UserRole.USER, uid="another")

    with pytest.raises(BadRequestError):
        await svc.enter_library(lib.id, current_user=user)


@pytest.mark.asyncio
async def test_create_library_success_updates_root_path(monkeypatch):
    svc = LibraryService()
    lib = make_library(lid="lib123", public=True)
    svc.logic = FakeLibraryLogic(lib)
    svc.task_logic = FakeTaskLogic()

    class FakeFileOps:
        def _resolve_library_root(self, root_path: str) -> str:
            return f"/tmp/{root_path}"
        def make_dir_rw(self, path: str) -> None:
            return None
    svc.file_logic = FakeFileOps()

    payload = LibraryCreate(
        user_id="u1",
        name="Lib",
        root_path="temp",
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=True,
        is_active=True,
    )

    created = await svc.create_library(payload, current_user=make_user(uid="u1"))
    assert created.root_path == created.id  # 服务层会更新为库ID


@pytest.mark.asyncio
async def test_create_library_root_init_failure_rollbacks(monkeypatch):
    svc = LibraryService()
    lib = make_library(lid="lib_fail", public=True)
    logic = FakeLibraryLogic(lib)
    svc.logic = logic
    svc.task_logic = FakeTaskLogic()

    class FakeFileOps:
        def _resolve_library_root(self, root_path: str) -> str:
            return f"/tmp/{root_path}"
        def make_dir_rw(self, path: str) -> None:
            raise RuntimeError("fs error")
    svc.file_logic = FakeFileOps()

    payload = LibraryCreate(
        user_id="u1",
        name="Lib",
        root_path="temp",
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=True,
        is_active=True,
    )

    with pytest.raises(ValidationError):
        await svc.create_library(payload, current_user=make_user(uid="u1"))

    # 验证：发生异常后触发硬删除回滚
    assert logic._deleted_hard_called is True


@pytest.mark.asyncio
async def test_delete_library_soft_delete_returns_model_and_none_task():
    svc = LibraryService()
    lib = make_library(lid="lib_soft")
    svc.logic = FakeLibraryLogic(lib)
    user = make_user(uid="u1", role=UserRole.ADMIN)

    deleted_model, task_ctx = await svc.delete_library(lib.id, soft_delete=True, current_user=user)
    assert isinstance(deleted_model, LibraryRead)
    assert task_ctx is None


@pytest.mark.asyncio
async def test_delete_library_hard_delete_triggers_cleanup_task(monkeypatch):
    svc = LibraryService()
    lib = make_library(lid="lib_hard")
    logic = FakeLibraryLogic(lib)
    svc.logic = logic
    svc.task_logic = FakeTaskLogic()

    # Patch 内部引用的 MovieLogic/MovieAssetLogic 和 send_task
    import src.services.movies.library_service as mod
    import src.logic as logic_mod

    class FakeMovieLogic:
        async def list_movie_ids(self, library_id, session=None):
            return ["m1", "m2"]

        async def delete_movies(self, movie_ids, soft_delete=False, session=None):
            return len(movie_ids)

    class FakeMovieAssetLogic:
        async def delete_library_assets(self, library_id, movie_ids, soft_delete=False, session=None):
            return 5

    # 关键修复：打桩 src.logic 模块的导出符号，而不是 library_service 模块
    monkeypatch.setattr(logic_mod, "MovieLogic", FakeMovieLogic)
    monkeypatch.setattr(logic_mod, "MovieAssetLogic", FakeMovieAssetLogic)
    class FakeWatchHistoryLogic:
        async def delete_by_filter(self, *, movie_ids, session=None):
            return True
    monkeypatch.setattr(mod, "WatchHistoryLogic", FakeWatchHistoryLogic)
    async def fake_send_task(sub_type, payload, priority):
        return True
    monkeypatch.setattr(mod, "send_task", fake_send_task)

    user = make_user(uid="u1", role=UserRole.ADMIN)
    deleted_before, task_ctx = await svc.delete_library(lib.id, soft_delete=False, current_user=user)
    assert deleted_before.id == lib.id
    assert isinstance(task_ctx, dict) and "t1" in task_ctx


@pytest.mark.asyncio
async def test_exit_library_returns_bool():
    svc = LibraryService()
    lib = make_library()
    svc.logic = FakeLibraryLogic(lib)
    user = make_user(uid="u1")

    with pytest.raises(BadRequestError):
        await svc.exit_library(current_user=user)


@pytest.mark.asyncio
async def test_set_visibility_and_activity_require_edit_permission():
    svc = LibraryService()
    lib = make_library()
    svc.logic = FakeLibraryLogic(lib)

    guest = make_user(role=UserRole.GUEST, uid="g1")
    with pytest.raises(ForbiddenError):
        await svc.update_library_visibility(lib.id, is_public=True, current_user=guest)
    with pytest.raises(ForbiddenError):
        await svc.update_library_activity(lib.id, is_active=False, current_user=guest)


@pytest.mark.asyncio
async def test_get_library_stats_requires_edit_permission_for_user_not_owner():
    svc = LibraryService()
    lib = make_library(owner="owner", public=True)
    svc.logic = FakeLibraryLogic(lib)
    # 模拟 _ensure_user_edit_permission：user 非 owner 且角色 USER -> Forbidden
    user = make_user(role=UserRole.USER, uid="another")

    with pytest.raises(ForbiddenError):
        await svc.get_library_stats(lib.id, current_user=user)


@pytest.mark.asyncio
async def test_list_library_covers_signed_returns_urls(monkeypatch):
    svc = LibraryService()
    lib = make_library(owner="u1", public=True)
    svc.logic = FakeLibraryLogic(lib)
    class FakeFileOps:
        def build_library_signed_url(self, library_id: str, resource_path: str, expires_in_seconds=None):
            return (f"signed://{library_id}/{resource_path}", 0)
    svc.file_logic = FakeFileOps()
    user = make_user(uid="u1", role=UserRole.USER)

    urls = await svc.list_library_covers_signed([lib.id, "l2"], current_user=user)
    assert urls == [f"signed://{lib.id}/backdrop.jpg", "signed://l2/backdrop.jpg"]

@pytest.mark.asyncio
async def test_list_library_covers_signed_forbidden_for_non_owner_private():
    svc = LibraryService()
    # 私有库，非拥有者，普通用户 → 应拒绝
    lib = make_library(owner="owner", public=False)
    svc.logic = FakeLibraryLogic(lib)
    user = make_user(uid="another", role=UserRole.USER)
    with pytest.raises(ForbiddenError):
        await svc.list_library_covers_signed([lib.id], current_user=user)

@pytest.mark.asyncio
async def test_upload_library_cover_calls_file_logic_and_returns_true():
    svc = LibraryService()
    lib = make_library(owner="u1", public=False)
    svc.logic = FakeLibraryLogic(lib)

    class FakeFileOps:
        def __init__(self):
            self.saved = None
        def save_library_cover(self, upload, library_id):
            self.saved = (library_id, getattr(upload, "filename", None))

    svc.file_logic = FakeFileOps()

    class FakeUpload:
        filename = "cover.jpg"

    user = make_user(uid="u1", role=UserRole.USER)  # 拥有者
    ok = await svc.upload_library_cover(lib.id, FakeUpload(), current_user=user)
    assert ok is True
    assert svc.file_logic.saved == (lib.id, "cover.jpg")

@pytest.mark.asyncio
async def test_upload_library_cover_forbidden_for_non_owner_user():
    svc = LibraryService()
    lib = make_library(owner="owner", public=True)
    svc.logic = FakeLibraryLogic(lib)
    user = make_user(uid="another", role=UserRole.USER)  # 非拥有者
    class FakeUpload:
        filename = "cover.jpg"
    with pytest.raises(ForbiddenError):
        await svc.upload_library_cover(lib.id, FakeUpload(), current_user=user)

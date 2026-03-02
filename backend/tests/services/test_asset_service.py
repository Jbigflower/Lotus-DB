import pytest
from datetime import datetime, timezone

from src.services.movies.asset_service import MovieAssetService
from src.models import (
    UserRead,
    UserRole,
    LibraryRead,
    LibraryType,
    AssetType,
    AssetStoreType,
    AssetRead,
    AssetCreate,
    AssetUpdate,
    AssetPageResult,
)
from src.core.exceptions import ForbiddenError


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
        root_path="/tmp/lib_root",
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


def make_asset(
    aid="a1", lib_id="l1", movie_id="m1", kind: AssetType = AssetType.VIDEO
) -> AssetRead:
    return AssetRead(
        id=aid,
        library_id=lib_id,
        movie_id=movie_id,
        type=kind,
        name="asset",
        path=f"/tmp/lib_root/{movie_id}/{kind.value}/asset.ext",
        store_type=AssetStoreType.LOCAL,
        actual_path=f"/tmp/lib_root/{movie_id}/{kind.value}/asset.ext",
        description="",
        metadata=None,
        is_deleted=False,
        deleted_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class FakeRepoTx:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeRepo:
    def transaction(self):
        return FakeRepoTx()


class FakeAssetLogic:
    def __init__(self, asset: AssetRead):
        self._asset = asset
        self.repo = FakeRepo()

    async def get_asset(self, asset_id, session=None):
        return self._asset

    async def update_asset(self, asset_id, patch: AssetUpdate, session=None):
        data = self._asset.model_dump()
        for k, v in patch.model_dump(exclude_unset=True).items():
            data[k] = v
        self._asset = AssetRead(**data)
        return self._asset

    async def get_assets(self, asset_ids, session=None):
        # 返回不同 ID 的副本列表
        items = []
        for i, aid in enumerate(asset_ids):
            a = self._asset.model_dump()
            a["id"] = aid
            items.append(AssetRead(**a))
        return items

    async def delete_assets(self, asset_ids, soft_delete=True, session=None):
        return len(asset_ids)

    async def delete_asset(self, asset_id, soft_delete=True, session=None):
        return True

    async def restore_assets(self, asset_ids, session=None):
        # 无需返回，服务层随后会 get_assets
        return None

    async def create_asset(self, payload: AssetCreate, session=None):
        data = payload.model_dump()
        data.update(
            {
                "id": "new_asset",
                "metadata": None,
                "is_deleted": False,
                "deleted_at": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return AssetRead(**data)

    async def search_assets(self, **kwargs):
        return AssetPageResult(items=[self._asset], total=1, page=1, size=20, pages=1)

    async def list_movies_assets(self, movie_ids, **kwargs):
        return [self._asset for _ in movie_ids]


@pytest.mark.asyncio
async def test_get_asset_permission_denied_private():
    svc = MovieAssetService()
    svc.logic = FakeAssetLogic(make_asset())
    lib = make_library(public=False, owner="owner")
    user = make_user(role=UserRole.USER, uid="another")
    with pytest.raises(ForbiddenError):
        await svc.get_asset("a1", current_user=user, current_library=lib)


@pytest.mark.asyncio
async def test_get_asset_returns_model():
    svc = MovieAssetService()
    asset = make_asset()
    svc.logic = FakeAssetLogic(asset)
    lib = make_library(public=True)
    user = make_user()
    got = await svc.get_asset(asset.id, current_user=user, current_library=lib)
    assert isinstance(got, AssetRead) and got.id == asset.id


@pytest.mark.asyncio
async def test_update_movie_asset_updates_name():
    svc = MovieAssetService()
    asset = make_asset()
    svc.logic = FakeAssetLogic(asset)
    lib = make_library(owner="u1", public=True)
    user = make_user(uid="u1")
    patch = AssetUpdate(name="new-name")
    updated = await svc.update_movie_asset(asset.id, patch, current_user=user, current_library=lib)
    assert isinstance(updated, AssetRead) and updated.name == "new-name"


@pytest.mark.asyncio
async def test_delete_movie_assets_soft_delete_counts():
    svc = MovieAssetService()
    svc.logic = FakeAssetLogic(make_asset())
    lib = make_library(owner="u1")
    user = make_user(uid="u1")
    count = await svc.delete_movie_assets(["a1", "a2"], soft_delete=True, current_user=user, current_library=lib)
    assert count == 2


@pytest.mark.asyncio
async def test_delete_movie_assets_hard_delete_calls_fileops(monkeypatch):
    svc = MovieAssetService()
    base = make_asset(movie_id="mX")
    svc.logic = FakeAssetLogic(base)
    lib = make_library(owner="u1")
    user = make_user(uid="u1")

    deleted_paths = []

    import src.services.movies.asset_service as mod

    class FakeFileOps:
        def delete_file(self, path):
            deleted_paths.append(path)

    monkeypatch.setattr(mod, "FilmAssetFileOps", FakeFileOps)

    count = await svc.delete_movie_assets(["a1", "a2"], soft_delete=False, current_user=user, current_library=lib)
    assert count == 2
    # 两个资产均触发 delete_file
    assert len(deleted_paths) == 2
    assert all(path.endswith("/asset.ext") for path in deleted_paths)


@pytest.mark.asyncio
async def test_delete_movie_asset_hard_delete_calls_fileops(monkeypatch):
    svc = MovieAssetService()
    asset = make_asset()
    svc.logic = FakeAssetLogic(asset)
    lib = make_library(owner="u1")
    user = make_user(uid="u1")

    deleted_paths = []

    import src.services.movies.asset_service as mod

    class FakeFileOps:
        def delete_file(self, path):
            deleted_paths.append(path)

    monkeypatch.setattr(mod, "FilmAssetFileOps", FakeFileOps)

    ok = await svc.delete_movie_asset(asset.id, soft_delete=False, current_user=user, current_library=lib)
    assert ok is True
    assert deleted_paths == [asset.actual_path]


@pytest.mark.asyncio
async def test_restore_movie_assets_returns_list():
    svc = MovieAssetService()
    asset = make_asset()
    svc.logic = FakeAssetLogic(asset)
    lib = make_library(owner="u1")
    user = make_user(uid="u1")
    restored = await svc.restore_movie_assets(["a1", "a2"], current_user=user, current_library=lib)
    assert isinstance(restored, list) and len(restored) == 2
    assert restored[0].id == "a1" and restored[1].id == "a2"


@pytest.mark.asyncio
async def test_upload_movie_asset_with_url_sends_tasks_and_creates(monkeypatch):
    svc = MovieAssetService()
    lib = make_library(owner="u1")
    user = make_user(uid="u1")
    # 基础资产（仅用于 FakeLogic 的返回）
    svc.logic = FakeAssetLogic(make_asset(movie_id="m1"))

    import src.services.movies.asset_service as mod

    # 捕获任务发送
    sent = []

    async def fake_send_task(name, payload, priority):
        sent.append((name, payload, priority))
        return f"{name}-id"

    monkeypatch.setattr(mod, "send_task", fake_send_task)

    class FakeFileOps:
        def smart_download_file_to_library(self, url, save_path, kind, name):
            # 返回目标路径与保存名
            return (f"{save_path}/{name or 'dl.ext'}", name or "dl.ext", "masked.url")

    monkeypatch.setattr(mod, "FilmAssetFileOps", FakeFileOps)

    payload = AssetCreate(
        library_id="ignored",  # 服务层会重写为 current_library.id
        movie_id="m1",
        type=AssetType.VIDEO,
        name="video.mp4",
        path="/ignored",
        store_type=AssetStoreType.LOCAL,
        actual_path=None,
        description="",
    )
    created, tasks = await svc.upload_movie_asset(
        payload,
        context={"url": "https://example.com/video.mp4"},
        current_user=user,
        current_library=lib,
    )
    assert isinstance(created, AssetRead)
    assert "extract_metadata" in tasks and "generate_thumb_sprite" in tasks
    assert tasks["extract_metadata"].endswith("extract_metadata-id")
    assert tasks["generate_thumb_sprite"].endswith("generate_thumb_sprite-id")
    # 路径由 FakeFileOps 决定
    assert created.path.startswith(f"{lib.root_path}/m1/{AssetType.VIDEO.value}")
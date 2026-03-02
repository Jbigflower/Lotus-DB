import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.movie_assets import router as assets_router
import src.routers.movie_assets as assets_mod
from src.core.dependencies import get_current_user, get_current_library
from src.models import (
    LibraryRead,
    LibraryType,
    UserRead,
    UserRole,
    AssetRead,
    AssetType,
    AssetStoreType,
    AssetPageResult,
    AssetUpdate,
)


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


def make_asset(aid="a1", lib_id="l1", movie_id="m1") -> AssetRead:
    return AssetRead(
        id=aid,
        library_id=lib_id,
        movie_id=movie_id,
        type=AssetType.VIDEO,
        name="asset",
        path=f"/tmp/lib_root/{movie_id}/video/asset.ext",
        store_type=AssetStoreType.LOCAL,
        actual_path=f"/tmp/lib_root/{movie_id}/video/asset.ext",
        description="",
        metadata=None,
        is_deleted=False,
        deleted_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class FakeService:
    def __init__(self, asset: AssetRead):
        self._asset = asset

    async def list_movie_assets_page(self, movie_id: str, **kwargs):
        return AssetPageResult(items=[self._asset], total=1, page=1, size=20, pages=1)

    async def get_asset(self, asset_id: str, **kwargs):
        return self._asset

    async def upload_movie_asset(self, data, **kwargs):
        # 返回创建的资产与任务信息
        return self._asset, {"extract_metadata": "id1", "generate_thumb_sprite": "id2"}

    async def update_movie_asset(self, asset_id: str, patch: AssetUpdate, **kwargs):
        d = self._asset.model_dump()
        for k, v in patch.model_dump(exclude_unset=True).items():
            d[k] = v
        self._asset = AssetRead(**d)
        return self._asset

    async def delete_movie_assets(self, asset_ids, soft_delete=True, **kwargs):
        return len(asset_ids)

    async def delete_movie_asset(self, asset_id, soft_delete=True, **kwargs):
        return True

    async def restore_movie_assets(self, asset_ids, **kwargs):
        # 返回多个副本
        return [self._asset for _ in asset_ids]


def make_app(fake_user: UserRead, fake_library: LibraryRead, fake_service: FakeService) -> TestClient:
    app = FastAPI()
    app.include_router(assets_router)

    async def _fake_get_current_user():
        return fake_user

    async def _fake_get_current_library():
        return fake_library

    app.dependency_overrides[get_current_user] = _fake_get_current_user
    app.dependency_overrides[get_current_library] = _fake_get_current_library

    # 替换模块级 service
    assets_mod.asset_service = fake_service
    return TestClient(app)


def test_list_movie_assets_returns_page(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    resp = client.get(f"/assets/movies/{asset.movie_id}?page=1&size=20")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert page["items"][0]["id"] == asset.id


def test_get_asset_returns_model(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    resp = client.get(f"/assets/{asset.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == asset.id


def test_create_movie_asset_with_url_returns_dict(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    form = {"type": AssetType.VIDEO.value, "url": "https://example.com/file.mp4", "name": "nm"}
    resp = client.post(f"/assets/{asset.movie_id}", data=form)
    assert resp.status_code == 200
    data = resp.json()
    assert "asset" in data and "tasks" in data
    assert data["asset"]["id"] == asset.id
    assert "extract_metadata" in data["tasks"]


def test_update_movie_asset_returns_model(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    resp = client.patch(f"/assets/{asset.id}", json={"name": "new"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "new"


def test_delete_movie_assets_bulk_returns_dict(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    body = {"asset_ids": ["a1", "a2"]}
    resp = client.request("DELETE", "/assets/bulk?soft_delete=true", json=body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["message"] == "删除完成" and result["success"] == 2 and result["failed"] == 0


def test_delete_movie_asset_returns_dict(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    resp = client.delete(f"/assets/{asset.id}?soft_delete=false")
    assert resp.status_code == 200
    result = resp.json()
    assert result["message"] == "删除完成" and result["success"] == 1 and result["failed"] == 0


def test_restore_movie_assets_returns_list(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    body = {"asset_ids": ["a1", "a2"]}
    resp = client.post("/assets/restore", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 2
    assert data[0]["id"] == asset.id


def test_create_movie_asset_invalid_url_returns_400(monkeypatch):
    asset = make_asset()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(asset))
    form = {"type": AssetType.VIDEO.value, "url": "ftp://bad.url/file", "name": "nm"}
    resp = client.post(f"/assets/{asset.movie_id}", data=form)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "非法 URL" in detail
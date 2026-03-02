import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.libraries import router as libraries_router
import src.routers.libraries as libraries_mod
from src.core.dependencies import get_current_user
from src.models import (
    LibraryRead,
    LibraryType,
    LibraryPageResult,
    UserRead,
    UserRole,
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


class FakeService:
    def __init__(self, lib: LibraryRead):
        self._lib = lib

    async def get_current_library(self, *, current_user):
        return self._lib

    async def enter_library(self, library_id: str, *, current_user):
        return self._lib

    async def list_libraries(self, **kwargs):
        return LibraryPageResult(items=[self._lib], total=1, page=1, size=20, pages=1)

    async def get_library(self, library_id: str, current_user):
        return self._lib

    async def get_library_stats(self, library_id: str, *, current_user):
        return {"movies": 10, "assets": 5}

    # 新增：批量封面签名与上传封面
    async def list_library_covers_signed(self, ids, *, current_user):
        return [f"signed://{i}/backdrop.jpg" for i in ids]

    async def upload_library_cover(self, library_id: str, file, *, current_user):
        return True


def make_app(fake_user: UserRead, fake_service: FakeService) -> TestClient:
    app = FastAPI()
    app.include_router(libraries_router)
    # 覆盖认证依赖
    async def _fake_get_current_user():
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_get_current_user
    # 替换模块级 service
    libraries_mod.service = fake_service
    return TestClient(app)


def test_enter_library_returns_model(monkeypatch):
    lib = make_library()
    client = make_app(fake_user=make_user(), fake_service=FakeService(lib))
    resp = client.post(f"/api/v1/libraries/{lib.id}/enter")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == lib.id and data["name"] == "Lib"


def test_get_current_library_returns_model(monkeypatch):
    lib = make_library()
    client = make_app(fake_user=make_user(), fake_service=FakeService(lib))
    resp = client.get("/api/v1/libraries/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == lib.id


def test_list_libraries_returns_page(monkeypatch):
    lib = make_library()
    client = make_app(fake_user=make_user(), fake_service=FakeService(lib))
    resp = client.get("/api/v1/libraries/?library_type=movie")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert page["items"][0]["id"] == lib.id


def test_get_library_stats_returns_dict(monkeypatch):
    lib = make_library()
    client = make_app(fake_user=make_user(), fake_service=FakeService(lib))
    resp = client.get(f"/api/v1/libraries/{lib.id}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["movies"] == 10 and stats["assets"] == 5


def test_get_library_covers_signed_returns_list(monkeypatch):
    lib = make_library()
    client = make_app(fake_user=make_user(), fake_service=FakeService(lib))
    resp = client.post("/api/v1/libraries/covers/sign", json=[lib.id, "l2"])
    assert resp.status_code == 200
    urls = resp.json()
    assert isinstance(urls, list) and len(urls) == 2
    assert urls[0].startswith("signed://") and urls[0].endswith("/backdrop.jpg")


def test_upload_library_cover_returns_ok(monkeypatch):
    lib = make_library()
    client = make_app(fake_user=make_user(), fake_service=FakeService(lib))
    files = {"file": ("cover.jpg", b"fake-binary", "image/jpeg")}
    resp = client.post(f"/api/v1/libraries/{lib.id}/cover", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True and "上传封面成功" in data["message"]
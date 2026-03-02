import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.movies import router as movies_router
import src.routers.movies as movies_mod
from src.core.dependencies import get_current_user, get_current_library
from src.models import (
    LibraryRead,
    LibraryType,
    UserRead,
    UserRole,
    MovieRead,
    MoviePageResult,
    TaskRead,
    TaskType,
    TaskSubType,
    TaskPriority,
    TaskStatus,
    ProgressInfo,
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


def make_movie(mid="m1", lib_id="l1", title="T") -> MovieRead:
    return MovieRead(
        id=mid,
        library_id=lib_id,
        title=title,
        title_cn="TT",
        directors=[],
        actors=[],
        description="",
        description_cn="",
        release_date=None,
        genres=[],
        metadata={},
        rating=8.0,
        tags=[],
        has_poster=False,
        has_backdrop=False,
        has_thumbnail=False,
        is_deleted=False,
        deleted_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class FakeService:
    def __init__(self, movie: MovieRead):
        self._movie = movie

    async def list_movies(self, **kwargs):
        return MoviePageResult(items=[self._movie], total=1, page=1, size=20, pages=1)

    async def list_recycle_bin_movies(self, **kwargs):
        return MoviePageResult(items=[self._movie], total=1, page=1, size=20, pages=1)

    async def get_movie(self, movie_id: str, **kwargs):
        return self._movie

    async def create_movie(self, data, **kwargs):
        return self._movie

    async def import_movies_from_file(self, file, **kwargs):
        return TaskRead(
            id="t1",
            name="导入电影",
            description="导入电影",
            task_type=TaskType.IMPORT,
            sub_type=TaskSubType.MOVIE_IMPORT,
            priority=TaskPriority.NORMAL,
            parameters={},
            status=TaskStatus.PENDING,
            progress=ProgressInfo(),
            result={},
            user_id="u1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ), {"task_id": "t1"}

    async def update_movies_by_ids(self, movie_ids, patch, **kwargs):
        m = self._movie.model_dump()
        for k, v in patch.model_dump(exclude_unset=True).items():
            m[k] = v
        return [MovieRead(**m) for _ in movie_ids]

    async def delete_movies_by_ids(self, movie_ids, soft_delete=True, **kwargs):
        msg = "软删除完成" if soft_delete else "硬删除完成"
        return {"message": msg, "success": len(movie_ids), "failed": 0}

    async def restore_movies_by_ids(self, movie_ids, **kwargs):
        return [self._movie for _ in movie_ids]


def make_app(fake_user: UserRead, fake_library: LibraryRead, fake_service: FakeService) -> TestClient:
    app = FastAPI()
    app.include_router(movies_router)

    async def _fake_get_current_user():
        return fake_user

    async def _fake_get_current_library():
        return fake_library

    app.dependency_overrides[get_current_user] = _fake_get_current_user
    app.dependency_overrides[get_current_library] = _fake_get_current_library

    # 替换模块级 service
    movies_mod.movie_service = fake_service
    return TestClient(app)


def test_list_movies_returns_page(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.get("/api/v1/movies/?page=1&size=20")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert page["items"][0]["id"] == movie.id


def test_get_movie_returns_model(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.get(f"/api/v1/movies/{movie.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == movie.id and data["title"] == movie.title


def test_create_movie_returns_model(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    # 注意：路由层会构造 MovieCreate，因此请求体需包含 library_id 和 title
    payload = {"library_id": "lX", "title": "T"}
    resp = client.post("/api/v1/movies/", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == movie.id


def test_import_movies_returns_task(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    files = {"file": ("movies.json", '[{"title":"A"}]', "application/json")}
    resp = client.post("/api/v1/movies/bulk?library_id=l1", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "t1"


def test_update_movie_returns_model(monkeypatch):
    movie = make_movie(title="Old")
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.patch(f"/api/v1/movies/{movie.id}", json={"title": "New"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New"


def test_update_movies_batch_returns_list(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    payload = {"movie_ids": ["m1", "m2"], "patch": {"title": "New"}}
    resp = client.patch("/api/v1/movies/batch", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 2
    assert all(item["title"] == "New" for item in data)


def test_delete_movie_returns_dict(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.delete(f"/api/v1/movies/{movie.id}?soft_delete=true")
    assert resp.status_code == 200
    result = resp.json()
    assert result["message"] == "软删除完成" and result["success"] == 1


def test_delete_movies_bulk_returns_dict(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.request("DELETE", "/api/v1/movies/bulk?soft_delete=false", json=["m1", "m2"])
    assert resp.status_code == 200
    result = resp.json()
    assert result.get("message", "").strip() == "硬删除完成"


def test_restore_movies_returns_list(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.post("/api/v1/movies/restore", json=["m1", "m2"])
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) == 2

def test_list_recycle_bin_movies_returns_page(monkeypatch):
    movie = make_movie()
    client = make_app(fake_user=make_user(), fake_library=make_library(), fake_service=FakeService(movie))
    resp = client.get("/api/v1/movies/recycle-bin?page=1&size=20")
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1 and len(page["items"]) == 1
    assert page["items"][0]["id"] == movie.id

import pytest
import os
import json
from datetime import datetime, timezone

from src.services.movies.movie_service import MovieService
from src.models import (
    UserRead,
    UserRole,
    LibraryRead,
    LibraryType,
    LibraryPageResult,
    MovieRead,
    MovieCreate,
    MovieUpdate,
    MoviePageResult,
)
from src.core.exceptions import ForbiddenError, BadRequestError


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


class FakeRepoTx:
    async def __aenter__(self):
        return "session"

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeRepo:
    def transaction(self):
        return FakeRepoTx()


class FakeMovieLogic:
    def __init__(self, movie: MovieRead):
        self._movie = movie
        self.repo = FakeRepo()

    async def get_movies(self, movie_ids, session=None):
        base = self._movie.model_dump()
        items = []
        for mid in movie_ids:
            data = dict(base)
            data["id"] = mid
            items.append(MovieRead(**data))
        return items

    async def list_movies(self, **kwargs):
        return MoviePageResult(items=[self._movie], total=1, page=1, size=20, pages=1)

    async def get_movie(self, movie_id, session=None):
        data = self._movie.model_dump()
        data["id"] = movie_id
        return MovieRead(**data)

    async def create_movie(self, payload: MovieCreate, session=None):
        data = self._movie.model_dump()
        data["library_id"] = payload.library_id
        return MovieRead(**data)

    async def update_movies(self, movie_ids, patch_dict, session=None):
        m = self._movie.model_dump()
        for k, v in patch_dict.items():
            m[k] = v
        items = []
        for mid in movie_ids:
            data = dict(m)
            data["id"] = mid
            items.append(MovieRead(**data))
        return items

    async def delete_movies(self, movie_ids, soft_delete=True, session=None):
        return len(movie_ids)

    async def restore_by_ids(self, movie_ids, session=None):
        base = self._movie.model_dump()
        items = []
        for mid in movie_ids:
            data = dict(base)
            data["id"] = mid
            items.append(MovieRead(**data))
        return items


class FakeTaskInfo:
    id = "t1"


class FakeTaskLogic:
    async def create_task(self, task_create):
        return FakeTaskInfo()

class FakeCollectionLogic:
    async def get_user_collections(self, user_id):
        return []


class FakeLibraryLogic:
    def __init__(self, libraries):
        self._libs = {lib.id: lib for lib in libraries}

    async def get_library(self, library_id: str, session=None):
        return self._libs[library_id]

    async def list_libraries(
        self,
        *,
        role,
        user_id,
        only_me: bool,
        query=None,
        library_type=None,
        is_active=None,
        is_deleted=None,
        auto_import=None,
        page: int = 1,
        page_size: int = 10,
    ):
        items = list(self._libs.values())
        return LibraryPageResult(items=items, total=len(items), page=page, size=page_size, pages=1)


class FakeUploadFile:
    def __init__(self, payload):
        self._payload = payload  # python obj or raw bytes marker

    async def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


@pytest.mark.asyncio
async def test_list_movies_no_accessible_libraries_returns_empty_page():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    svc.library_logic = FakeLibraryLogic([])
    svc.collection_logic = FakeCollectionLogic()
    user = make_user()
    page = await svc.list_movies(current_user=user)
    assert isinstance(page, MoviePageResult)
    assert page.total == 0 and page.items == []


@pytest.mark.asyncio
async def test_list_movies_permission_denied_private():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    lib = make_library(public=False, owner="owner")
    svc.library_logic = FakeLibraryLogic([lib])
    svc.collection_logic = FakeCollectionLogic()
    user = make_user(role=UserRole.USER, uid="another")
    with pytest.raises(ForbiddenError):
        await svc.list_movies(current_user=user, library_id=lib.id)


@pytest.mark.asyncio
async def test_list_movies_returns_page():
    svc = MovieService()
    movie = make_movie()
    svc.logic = FakeMovieLogic(movie)
    lib = make_library(public=True)
    svc.library_logic = FakeLibraryLogic([lib])
    svc.collection_logic = FakeCollectionLogic()
    page = await svc.list_movies(current_user=make_user(), library_id=lib.id)
    assert page.total == 1 and page.items[0].id == movie.id


@pytest.mark.asyncio
async def test_get_movie_permission_denied_private():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie(lib_id="l1"))
    lib = make_library(public=False, owner="owner")
    lib.id = "l1"
    svc.library_logic = FakeLibraryLogic([lib])
    svc.collection_logic = FakeCollectionLogic()
    user = make_user(uid="another", role=UserRole.USER)
    with pytest.raises(ForbiddenError):
        await svc.get_movie("m1", current_user=user)


@pytest.mark.asyncio
async def test_create_movie_uses_payload_library_id(monkeypatch):
    svc = MovieService()
    movie = make_movie()
    svc.logic = FakeMovieLogic(movie)
    lib = make_library(lid="lib1", owner="u1", public=True)
    svc.library_logic = FakeLibraryLogic([lib])
    svc.collection_logic = FakeCollectionLogic()
    svc.task_logic = FakeTaskLogic()
    user = make_user(uid="u1")
    payload = MovieCreate(library_id=lib.id, title="T")
    import src.services.movies.movie_service as mod
    async def fake_send_task(name, payload, priority):
        return True
    monkeypatch.setattr(mod, "send_task", fake_send_task)
    created, _task_id = await svc.create_movie(payload, current_user=user)
    assert isinstance(created, MovieRead)
    assert created.library_id == lib.id


@pytest.mark.asyncio
async def test_import_movies_bad_json_raises():
    svc = MovieService()
    svc.task_logic = FakeTaskLogic()
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)
    bad_file = FakeUploadFile(b"not a json")
    with pytest.raises(BadRequestError):
        await svc.import_movies_from_file(bad_file, current_user=user, library_id=lib.id)


@pytest.mark.asyncio
async def test_import_movies_bad_shape_raises():
    svc = MovieService()
    svc.task_logic = FakeTaskLogic()
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)
    not_list_file = FakeUploadFile({"a": 1})
    with pytest.raises(BadRequestError):
        await svc.import_movies_from_file(not_list_file, current_user=user, library_id=lib.id)


@pytest.mark.asyncio
async def test_import_movies_success_sends_task(monkeypatch):
    svc = MovieService()
    svc.task_logic = FakeTaskLogic()
    movie = make_movie()
    svc.logic = FakeMovieLogic(movie)
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)

    import src.services.movies.movie_service as mod
    sent = []
    async def fake_send_task(name, payload, priority):
        sent.append((name, payload, priority))
        return True
    monkeypatch.setattr(mod, "send_task", fake_send_task)

    file = FakeUploadFile([{"title": "A"}, {"title": "B"}])
    task, info = await svc.import_movies_from_file(file, current_user=user, library_id=lib.id)
    assert task.id == "t1" and info["task_id"] == "t1"
    assert sent and sent[0][0] == "import_movies"
    payload = sent[0][1]
    assert len(payload["movies_data"]) == 2
    assert all(m["library_id"] == lib.id for m in payload["movies_data"])


@pytest.mark.asyncio
async def test_update_movies_by_ids_empty_raises():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)
    with pytest.raises(BadRequestError):
        await svc.update_movies_by_ids([], MovieUpdate(), current_user=user)


@pytest.mark.asyncio
async def test_update_movies_by_ids_updates_title():
    svc = MovieService()
    movie = make_movie(title="Old")
    svc.logic = FakeMovieLogic(movie)
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)
    res = await svc.update_movies_by_ids(["m1"], MovieUpdate(title="New"), current_user=user)
    assert len(res) == 1 and res[0].title == "New"


@pytest.mark.asyncio
async def test_delete_movies_soft_delete_counts():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)
    outcome = await svc.delete_movies_by_ids(["m1", "m2"], soft_delete=True, current_user=user)
    assert outcome["message"] == "软删除完成"
    assert outcome["success"] == 2 and outcome["failed"] == 0


@pytest.mark.asyncio
async def test_delete_movies_hard_delete_calls_assets_and_fileops(monkeypatch):
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)

    # Patch AssetLogic in src.logic and FileOps in service module
    import src.logic as logic_mod
    class FakeAssetLogic:
        async def delete_movies_assets(self, movie_ids, soft_delete=False, session=None):
            return len(movie_ids)

    monkeypatch.setattr(logic_mod, "MovieAssetLogic", FakeAssetLogic)

    import src.services.movies.movie_service as mod
    deleted_paths = []
    class FakeFileOps:
        def delete_dir(self, path):
            deleted_paths.append(path)
    svc.file_logic = FakeFileOps()
    class FakeWatchHistoryLogic:
        async def delete_by_filter(self, *, movie_ids, session=None):
            return True
    monkeypatch.setattr(mod, "WatchHistoryLogic", FakeWatchHistoryLogic)

    outcome = await svc.delete_movies_by_ids(["m1", "m2"], soft_delete=False, current_user=user)
    assert outcome["message"] == "硬删除完成"
    assert outcome["success"] == 2 and outcome["failed"] == 0
    assert set(deleted_paths) == {os.path.join("l1", "m1"), os.path.join("l1", "m2")}


@pytest.mark.asyncio
async def test_restore_movies_by_ids_returns_list():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    user = make_user(uid=lib.user_id)
    movies = await svc.restore_movies_by_ids(["m1", "m2"], current_user=user)
    assert len(movies) == 2 and [m.id for m in movies] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_edit_permission_guest_denied_on_update():
    svc = MovieService()
    svc.logic = FakeMovieLogic(make_movie())
    lib = make_library()
    svc.library_logic = FakeLibraryLogic([lib])
    guest = make_user(role=UserRole.GUEST, uid="g1")
    with pytest.raises(ForbiddenError):
        await svc.update_movies_by_ids(["m1"], MovieUpdate(title="X"), current_user=guest)

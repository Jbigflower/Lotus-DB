import pytest
from datetime import datetime, timezone
from hashlib import sha256
from tests.conftest import get_random_object_id

from src.logic.users.user_logic import UserLogic
import src.logic.users.user_logic as user_logic_mod
from src.core.exceptions import ConflictError, ValidationError, NotFoundError
from src.models import (
    UserInDB,
    UserRead,
    UserRole,
    UserCreate,
    UserPageResult,
)

def make_in_db(uid=None, username="tester", email="tester@example.com", hashed="hashed:old") -> UserInDB:
    if uid is None:
        uid = get_random_object_id()
    return UserInDB(
        id=uid,
        username=username,
        email=email,
        role=UserRole.USER,
        permissions=[],
        is_active=True,
        is_verified=True,
        settings={},
        hashed_password=hashed,
        last_login_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

class FakeUserRepo:
    soft_delete = True
    def __init__(self):
        self.users = {}
    async def find_by_id(self, user_id, session=None):
        return self.users.get(user_id)
    async def find_by_ids(self, ids, session=None):
        return [self.users[i] for i in ids if i in self.users]
    async def exists(self, filter_query, session=None):
        # 支持 username 或 email 唯一性
        for u in self.users.values():
            ok = True
            for k, v in filter_query.items():
                if getattr(u, k) != v:
                    ok = False
                    break
            if ok: return True
        return False
    async def insert_one(self, data: UserCreate, session=None):
        uid = get_random_object_id()
        item = make_in_db(uid=uid, username=data.username, email=data.email, hashed=data.hashed_password)
        self.users[uid] = item
        return item
    async def update_by_id(self, user_id, patch, session=None):
        u = self.users[user_id]
        for k, v in patch.items():
            setattr(u, k, v)
        u.updated_at = datetime.now(timezone.utc)
        self.users[user_id] = u
        return u
    async def delete_by_id(self, user_id, soft_delete=False, session=None):
        return 1 if self.users.pop(user_id, None) else 0
    async def count(self, filter_dict, session=None):
        # 简化计数：忽略过滤条件
        return len(self.users)
    async def find(self, filter_query=None, skip=0, limit=20, sort=None, projection=None, session=None):
        items = list(self.users.values())
        return items[skip: skip + limit]

class FakeUserRedisRepo:
    def __init__(self):
        self.store = {}
    async def get_user_info(self, user_id):
        return self.store.get(user_id)
    async def cache_user_info(self, user_id, payload):
        self.store[user_id] = payload
    async def clear_user_cache(self, user_id):
        self.store.pop(user_id, None)

class StubSettings:
    class App:
        secret_key = "SALT"
        algorithm = "sha256"
    app = App()

@pytest.mark.asyncio
async def test_hash_password_deterministic(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "get_settings", lambda: StubSettings())
    logic = UserLogic()
    out = logic._hash_password("pass123")
    expected = sha256(("SALT" + "pass123").encode("utf-8")).hexdigest()
    assert out == expected

@pytest.mark.asyncio
async def test_get_user_caches_and_returns(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    logic = UserLogic()
    u = make_in_db()
    logic.repo.users[u.id] = u
    got = await logic.get_user(u.id)
    assert isinstance(got, UserRead) and got.id == u.id
    cached = await logic.cache_repo.get_user_info(u.id)
    assert cached and cached["id"] == u.id

@pytest.mark.asyncio
async def test_create_user_conflict_username(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    logic = UserLogic()
    existed = make_in_db(username="alice", email="alice@example.com")
    logic.repo.users[existed.id] = existed
    with pytest.raises(ConflictError):
        await logic.create_user(UserCreate(username="alice", email="new@example.com", role=UserRole.USER, permissions=[], is_active=True, is_verified=True, settings={}, hashed_password="h"))

@pytest.mark.asyncio
async def test_change_password_validation(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "get_settings", lambda: StubSettings())
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    logic = UserLogic()
    u = make_in_db(hashed=logic._hash_password("oldpass"))
    logic.repo.users[u.id] = u

    from src.routers.schemas.user import UserPasswordChange
    bad = UserPasswordChange(old_password="wrong123", new_password="new123123")
    with pytest.raises(ValidationError):
        await logic.change_password(u.id, bad)

    good = UserPasswordChange(old_password="oldpass", new_password="new13333")
    updated = await logic.change_password(u.id, good)
    assert isinstance(updated, UserRead)

@pytest.mark.asyncio
async def test_update_identity_conflict_email(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    logic = UserLogic()
    u1 = make_in_db(username="u1", email="a@example.com")
    u2 = make_in_db(username="u2", email="b@example.com")
    logic.repo.users[u1.id] = u1
    logic.repo.users[u2.id] = u2

    from src.routers.schemas.user import UserIdentityUpdate
    with pytest.raises(ConflictError):
        await logic.update_username_or_email(u1.id, UserIdentityUpdate(email="b@example.com"))

@pytest.mark.asyncio
async def test_search_users_returns_page(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    logic = UserLogic()
    u1 = make_in_db(username="alice", email="alice@example.com")
    u2 = make_in_db(username="bob", email="bob@example.com")
    logic.repo.users[u1.id] = u1
    logic.repo.users[u2.id] = u2

    page = await logic.search_users(query="a", page=1, size=10)
    assert isinstance(page, UserPageResult) and page.total == 2 and len(page.items) <= 2

@pytest.mark.asyncio
async def test_delete_user_clears_cache(monkeypatch):
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    logic = UserLogic()
    u = make_in_db()
    logic.repo.users[u.id] = u
    await logic.cache_repo.cache_user_info(u.id, u.model_dump(exclude={"hashed_password"}))
    ok = await logic.delete_user(u.id)
    assert ok is True
    assert await logic.cache_repo.get_user_info(u.id) is None
import pytest
from datetime import datetime, timezone
from typing import List, Dict, Optional

from src.logic.users.auth_logic import AuthLogic, create_access_token
from src.models import UserCreate, UserInDB, UserRead, UserRole
from src.core.exceptions import UnauthorizedError

class FakeUserRepo:
    def __init__(self):
        self.users: Dict[str, UserInDB] = {}

    async def exists(self, filter_query: Dict, session=None) -> bool:
        for u in self.users.values():
            if "username" in filter_query and u.username == filter_query["username"]:
                return True
            if "email" in filter_query and u.email == filter_query["email"]:
                return True
        return False

    async def insert_one(self, payload: UserCreate, session=None) -> UserInDB:
        uid = f"u{len(self.users) + 1}"
        now = datetime.now(timezone.utc)
        u = UserInDB(
            id=uid,
            username=payload.username,
            email=payload.email,
            role=payload.role,
            permissions=payload.permissions,
            is_active=payload.is_active,
            is_verified=payload.is_verified,
            settings=payload.settings,
            hashed_password=payload.hashed_password,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )
        self.users[uid] = u
        return u

    async def find(self, filter_query: Dict, limit: int = 1, session=None) -> List[UserInDB]:
        res: List[UserInDB] = []
        for u in self.users.values():
            ok = True
            for k, v in filter_query.items():
                if getattr(u, k) != v:
                    ok = False
                    break
            if ok:
                res.append(u)
        if limit:
            return res[:limit]
        return res

    async def update_by_id(self, user_id: str, updates: Dict, session=None) -> UserInDB:
        u = self.users[user_id]
        for k, v in updates.items():
            setattr(u, k, v)
        u.updated_at = datetime.now(timezone.utc)
        self.users[user_id] = u
        return u


@pytest.mark.asyncio
async def test_login_and_verify_success(monkeypatch, patch_redis_client):
    # 替换 UserRepo
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    logic = AuthLogic()
    # 准备用户
    hashed = logic._hash_password("pass123")
    payload = UserCreate(
        username="alice", email="alice@example.com", role=UserRole.USER,
        permissions=[], is_active=True, is_verified=True, settings={}, hashed_password=hashed
    )
    created = await logic.register(payload)

    # 登录
    token, user_read, session_id = await logic.login("alice", "pass123", device_info={"user_agent": "pytest", "ip": "127.0.0.1", "platform": "test"})
    assert token and isinstance(user_read, UserRead) and session_id
    assert user_read.id.startswith("u")

    # 设备与用户缓存存在
    # info key
    info = await logic.user_cache.get_user_info(user_read.id)
    assert info and info["username"] == "alice"
    # device detail
    session_rec = await logic.user_cache.get_device_session(user_read.id, session_id)
    assert session_rec and session_rec["token"] == token

    # 验证 token
    current = await logic.verify_token(token)
    assert isinstance(current, UserRead)
    assert current.username == "alice"


@pytest.mark.asyncio
async def test_login_wrong_password_unauthorized(monkeypatch, patch_redis_client):
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    logic = AuthLogic()
    hashed = logic._hash_password("ok")
    payload = UserCreate(
        username="bob", email="bob@example.com", role=UserRole.USER,
        permissions=[], is_active=True, is_verified=True, settings={}, hashed_password=hashed
    )
    await logic.register(payload)

    with pytest.raises(UnauthorizedError):
        await logic.login("bob", "bad", device_info={"user_agent": "pytest"})


@pytest.mark.asyncio
async def test_logout_only_current_device(monkeypatch, patch_redis_client):
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    logic = AuthLogic()
    hashed = logic._hash_password("pass")
    payload = UserCreate(
        username="carol", email="carol@example.com", role=UserRole.USER,
        permissions=[], is_active=True, is_verified=True, settings={}, hashed_password=hashed
    )
    u = await logic.register(payload)

    # 两次登录（两设备）
    t1, user1, sid1 = await logic.login("carol", "pass", device_info={"user_agent": "UA1"})
    t2, user2, sid2 = await logic.login("carol", "pass", device_info={"user_agent": "UA2"})
    assert sid1 != sid2

    # 注销设备1
    await logic.logout(user_id=user1.id, session_id=sid1)

    # token1 失效；token2 仍有效
    with pytest.raises(UnauthorizedError):
        await logic.verify_token(t1)
    cur = await logic.verify_token(t2)
    assert cur.username == "carol"

    sessions = await logic.list_devices(user_id=user1.id)
    assert len(sessions) == 1 and sessions[0]["session_id"] == sid2


@pytest.mark.asyncio
async def test_revoke_all_except_current(monkeypatch, patch_redis_client):
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    logic = AuthLogic()
    hashed = logic._hash_password("pass")
    payload = UserCreate(
        username="dave", email="dave@example.com", role=UserRole.USER,
        permissions=[], is_active=True, is_verified=True, settings={}, hashed_password=hashed
    )
    u = await logic.register(payload)

    t1, _, s1 = await logic.login("dave", "pass", device_info={"user_agent": "UA1"})
    t2, _, s2 = await logic.login("dave", "pass", device_info={"user_agent": "UA2"})
    t3, _, s3 = await logic.login("dave", "pass", device_info={"user_agent": "UA3"})

    await logic.revoke_all_devices(user_id=u.id, except_session_id=s2)

    # s1/s3 无效；s2 有效
    for tk in [t1, t3]:
        with pytest.raises(UnauthorizedError):
            await logic.verify_token(tk)
    cur = await logic.verify_token(t2)
    assert cur.username == "dave"

    sessions = await logic.list_devices(user_id=u.id)
    assert len(sessions) == 1 and sessions[0]["session_id"] == s2


@pytest.mark.asyncio
async def test_rename_device(monkeypatch, patch_redis_client):
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    logic = AuthLogic()
    hashed = logic._hash_password("pass")
    payload = UserCreate(
        username="erin", email="erin@example.com", role=UserRole.USER,
        permissions=[], is_active=True, is_verified=True, settings={}, hashed_password=hashed
    )
    u = await logic.register(payload)

    t, _, sid = await logic.login("erin", "pass", device_info={"user_agent": "UA"})
    await logic.rename_device(user_id=u.id, session_id=sid, alias="My iPhone")

    rec = await logic.user_cache.get_device_session(u.id, sid)
    assert rec["alias"] == "My iPhone"
    sessions = await logic.list_devices(user_id=u.id)
    assert sessions[0]["alias"] == "My iPhone"


@pytest.mark.asyncio
async def test_verify_token_fallback_old_single_session(monkeypatch, patch_redis_client):
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    logic = AuthLogic()
    hashed = logic._hash_password("pass")
    payload = UserCreate(
        username="frank", email="frank@example.com", role=UserRole.USER,
        permissions=[], is_active=True, is_verified=True, settings={}, hashed_password=hashed
    )
    u = await logic.register(payload)

    # 构造无 sid 的旧 token，并缓存旧的单会话
    token = create_access_token(u.id)  # 不带 session_id
    user_read = UserRead(
        id=u.id,
        username="frank",
        email="frank@example.com",
        role=UserRole.USER,
        permissions=[],
        is_active=True,
        is_verified=True,
        settings={},
        hashed_password=None,
        last_login_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    user_info = user_read.model_dump()
    await logic.user_cache.cache_user_session(u.id, token, user_info)
    cur = await logic.verify_token(token)
    assert cur.username == "frank"
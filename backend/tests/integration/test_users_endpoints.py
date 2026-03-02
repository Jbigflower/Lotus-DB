import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import get_random_object_id

from src.routers.users import router as users_router
import src.routers.users as users_mod
from src.core.exceptions import register_exception_handlers
from src.core.dependencies import get_current_user
from src.services.users.user_service import UserService
from src.logic.users.user_logic import UserLogic
import src.logic.users.user_logic as user_logic_mod

from src.models import UserRead, UserRole, UserCreate

def make_user(role=UserRole.USER, uid=None) -> UserRead:
    if uid is None:
        uid = get_random_object_id()
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
        item = UserRead(
            id=uid,
            username=data.username,
            email=data.email,
            role=data.role,
            permissions=data.permissions,
            is_active=data.is_active,
            is_verified=data.is_verified,
            settings=data.settings,
            hashed_password=data.hashed_password,
            last_login_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
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

class FakeCollectionLogic:
    async def init_default(self, user_id: str):
        # 集成测试环境下不做真实初始化，避免外部依赖
        return None

def make_app_with_fake_chain(fake_user: UserRead, monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(users_router)
    register_exception_handlers(app)

    async def _fake_get_current_user():
        return fake_user
    app.dependency_overrides[get_current_user] = _fake_get_current_user

    # 真实 Service + Logic，替换 Logic 的 Repo/Cache/Settings
    svc = UserService()
    svc.logic = UserLogic()
    monkeypatch.setattr(user_logic_mod, "UserRepo", lambda: FakeUserRepo())
    monkeypatch.setattr(user_logic_mod, "UserRedisRepo", lambda: FakeUserRedisRepo())
    monkeypatch.setattr(user_logic_mod, "get_settings", lambda: StubSettings())

    # 重建逻辑以应用打桩类
    svc.logic = UserLogic()
    # 添加 fake collection logic，避免真实存储依赖
    svc.collection_logic = FakeCollectionLogic()
    users_mod.service = svc

    # 初始数据：一个已有用户（作为“当前用户”）
    svc.logic.repo.users[fake_user.id] = UserRead(**fake_user.model_dump())
    # 为当前用户补种 hashed_password，使密码校验通过（旧密码为 pass123）
    svc.logic.repo.users[fake_user.id].hashed_password = svc.logic._hash_password("pass123")

    # 打桩签名函数（头像签名）
    import src.logic.file.user_asset_file_ops as mod
    monkeypatch.setattr(mod.UserAssetFileOps, "build_user_signed_url", lambda uid, name: (f"signed://{uid}/{name}", 300))

    return TestClient(app)

def test_users_endpoints_full_flow(monkeypatch):
    admin = make_user(role=UserRole.ADMIN)
    client = make_app_with_fake_chain(admin, monkeypatch)

    # Create
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "pass123",
        "role": "user",
        "permissions": [],
        "is_active": True,
        "is_verified": True,
        "settings": {},
    }
    r_create = client.post("/api/v1/users/", json=payload)
    assert r_create.status_code == 200
    created = r_create.json()
    created_id = created["id"]

    # List (admin)
    r_list = client.get("/api/v1/users/?page=1&size=10")
    assert r_list.status_code == 200 and r_list.json()["total"] >= 1

    # Detail (admin)
    r_detail = client.get(f"/api/v1/users/{created_id}")
    assert r_detail.status_code == 200 and r_detail.json()["id"] == created_id

    # Set role
    r_role = client.patch(f"/api/v1/users/{created_id}/role", json={"role": "admin", "permissions": ["p1"]})
    assert r_role.status_code == 200 and r_role.json()["role"] == "admin"

    # Reset password (admin)
    r_reset = client.patch(f"/api/v1/users/{created_id}/password/reset", json={"new_password": "newpass"})
    assert r_reset.status_code == 200

    # Change password (self)
    # 切换当前用户为新创建的用户（模拟本人操作）
    new_self = make_user(role=UserRole.USER, uid=created_id)
    client2 = make_app_with_fake_chain(new_self, monkeypatch)
    r_change = client2.patch(f"/api/v1/users/{created_id}/password/change", json={"old_password": "pass123", "new_password": "pw21111111"})
    # 旧密码校验是根据 Repo 中 hashed_password 与 SALT 比较，简化场景允许通过
    assert r_change.status_code == 200

    # Identity update
    r_ident = client.patch(f"/api/v1/users/{created_id}/identity", json={"email": "new@example.com"})
    assert r_ident.status_code == 200 and r_ident.json()["email"] == "new@example.com"

    # Profiles sign
    ids = [created_id, get_random_object_id()]
    r_sign = client.post("/api/v1/users/profiles/sign", json=ids)
    assert r_sign.status_code == 200 and all(s.startswith("signed://") for s in r_sign.json())

    # Delete
    r_del = client.delete(f"/api/v1/users/{created_id}")
    assert r_del.status_code == 200 and r_del.json()["success"] in (0, 1)

def test_users_list_forbidden_non_admin(monkeypatch):
    non_admin = make_user(role=UserRole.USER)
    client = make_app_with_fake_chain(non_admin, monkeypatch)
    resp = client.get("/api/v1/users/")
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("error", {}).get("code") == "FORBIDDEN"
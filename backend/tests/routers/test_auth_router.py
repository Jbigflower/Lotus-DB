import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from src.routers.auth import router as auth_router
import src.routers.auth as auth_mod
from src.core.exceptions import register_exception_handlers
from src.models import UserCreate, UserInDB, UserRole

class FakeUserRepo:
    def __init__(self):
        self.users = {}

    async def exists(self, filter_query, session=None) -> bool:
        for u in self.users.values():
            if "username" in filter_query and u.username == filter_query["username"]:
                return True
            if "email" in filter_query and u.email == filter_query["email"]:
                return True
        return False

    async def insert_one(self, payload: UserCreate, session=None) -> UserInDB:
        uid = str(ObjectId())
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

    async def find(self, filter_query, limit: int = 1, session=None):
        res = []
        for u in self.users.values():
            ok = True
            for k, v in filter_query.items():
                if getattr(u, k) != v:
                    ok = False
                    break
            if ok:
                res.append(u)
        return res[:limit] if limit else res

    async def update_by_id(self, user_id: str, updates, session=None):
        u = self.users[user_id]
        for k, v in updates.items():
            setattr(u, k, v)
        u.updated_at = datetime.now(timezone.utc)
        self.users[user_id] = u
        return u


def make_app(monkeypatch) -> TestClient:
    # 替换 AuthLogic 的 UserRepo 为假实现（在构建 service 前执行）
    import src.logic.users.auth_logic as auth_logic_mod
    monkeypatch.setattr(auth_logic_mod, "UserRepo", FakeUserRepo)

    # 重建模块级 service 以使用假 Repo
    auth_mod.service = auth_mod.AuthService()

    app = FastAPI()
    app.include_router(auth_router)
    register_exception_handlers(app)
    return TestClient(app)


def test_register_login_devices_logout_flow(monkeypatch, patch_redis_client):
    client = make_app(monkeypatch)

    # 注册（自动登录）
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "pass12345",
        "role": "user",
        "permissions": [],
        "is_active": True,
        "is_verified": True,
        "settings": {},
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    token = data["access_token"]
    assert data["token_type"] == "bearer" and data["user"]["username"] == "alice" and data.get("session_id")

    # 设备列表（当前会话标记）
    resp2 = client.get("/auth/devices", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    sessions = resp2.json()
    assert len(sessions) == 1 and sessions[0]["is_current"] is True

    # 注销当前设备
    resp3 = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp3.status_code == 200

    # 注销后再次访问，需要 401
    resp4 = client.get("/auth/devices", headers={"Authorization": f"Bearer {token}"})
    assert resp4.status_code == 401
    body = resp4.json()
    # 依赖层抛 HTTPException 时返回 detail；Service/Router 异常则返回 error.code
    if "error" in body:
        assert body["error"].get("code") in ("UNAUTHORIZED", "ROUTER_ERROR")
    else:
        assert "detail" in body


def test_login_wrong_password_returns_401(monkeypatch, patch_redis_client):
    client = make_app(monkeypatch)
    # 先注册
    payload = {
        "username": "bob",
        "email": "bob@example.com",
        "password": "correctpw",
        "role": "user",
        "permissions": [],
        "is_active": True,
        "is_verified": True,
        "settings": {},
    }
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 200

    # 错误密码登录
    form = {"username": "bob", "password": "bad"}
    resp2 = client.post("/auth/login", data=form)
    assert resp2.status_code == 401
    body = resp2.json()
    assert body.get("error", {}).get("code") == "UNAUTHORIZED"


def test_devices_revoke_and_rename(monkeypatch, patch_redis_client):
    client = make_app(monkeypatch)
    # 注册并首次登录
    payload = {
        "username": "carol",
        "email": "carol@example.com",
        "password": "pass12345",
        "role": "user",
        "permissions": [],
        "is_active": True,
        "is_verified": True,
        "settings": {},
    }
    r1 = client.post("/auth/register", json=payload)
    assert r1.status_code == 200
    d1 = r1.json()
    tok1, sid1 = d1["access_token"], d1["session_id"]

    # 第二设备登录
    r2 = client.post("/auth/login", data={"username": "carol", "password": "pass12345"})
    assert r2.status_code == 200
    d2 = r2.json()
    tok2, sid2 = d2["access_token"], d2["session_id"]
    assert sid1 != sid2

    # 列出设备（用第二设备 token）
    r3 = client.get("/auth/devices", headers={"Authorization": f"Bearer {tok2}"})
    assert r3.status_code == 200
    sessions = r3.json()
    assert {s["session_id"] for s in sessions} == {sid1, sid2}
    current_sid = next(s for s in sessions if s["is_current"])["session_id"]
    assert current_sid == sid2

    # 撤销第一设备
    r4 = client.post(f"/auth/devices/revoke/{sid1}", headers={"Authorization": f"Bearer {tok2}"})
    assert r4.status_code == 200

    # 重命名第二设备
    r5 = client.patch(f"/auth/devices/{sid2}", headers={"Authorization": f"Bearer {tok2}"}, json={"alias": "My Mac"})
    assert r5.status_code == 200

    # 列表只剩第二设备且别名更新
    r6 = client.get("/auth/devices", headers={"Authorization": f"Bearer {tok2}"})
    assert r6.status_code == 200
    sessions2 = r6.json()
    assert len(sessions2) == 1 and sessions2[0]["session_id"] == sid2 and sessions2[0]["alias"] == "My Mac"

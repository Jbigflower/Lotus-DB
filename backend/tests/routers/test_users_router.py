import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import get_random_object_id

from src.routers.users import router as users_router
import src.routers.users as users_mod
from src.core.dependencies import get_current_user
from src.core.exceptions import register_exception_handlers, ForbiddenError
from src.models import (
    UserRead,
    UserRole,
    UserPageResult,
)

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

class FakeService:
    def __init__(self, user: UserRead | None = None):
        self.u = user or make_user()

    async def list_users(self, current_user, page=1, size=20, query=None, role=None, is_active=None, is_verified=None):
        return UserPageResult(items=[self.u], total=1, page=page, size=size, pages=1)

    async def get_user_detail(self, user_id: str, current_user):
        return self.u

    async def get_user_mappings(self, user_ids, current_user):
        return {uid: f"user-{uid[-4:]}" for uid in user_ids}

    async def create_user(self, payload, context, current_user):
        return self.u

    async def update_user_safety(self, user_id, patch, current_user):
        return self.u

    async def set_role_permissions(self, user_id, role, permissions, current_user):
        self.u.role = role or self.u.role
        self.u.permissions = permissions or []
        return self.u

    async def reset_password(self, user_id, payload, current_user):
        return self.u

    async def change_password(self, user_id, payload, current_user):
        return self.u

    async def update_identity(self, user_id, payload, current_user):
        if "username" in payload:
            self.u.username = payload["username"]
        if "email" in payload:
            self.u.email = payload["email"]
        return self.u

    async def delete_user(self, user_id, current_user):
        return (self.u, {"message": "用户删除成功", "success": 1, "failed": 0})

    async def set_user_active_status(self, user_id, is_active, current_user):
        self.u.is_active = is_active
        return self.u

    async def list_user_profiles_signed(self, ids, *, current_user):
        return [f"signed://{uid}/profile.jpg" for uid in ids]

    async def upload_user_profile(self, user_id, upload, *, current_user):
        return True

class FakeForbiddenService(FakeService):
    async def list_users(self, *args, **kwargs):
        raise ForbiddenError("无权限")

def make_app(fake_user: UserRead, fake_service: FakeService, *, with_handlers: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(users_router)

    async def _fake_get_current_user():
        return fake_user
    app.dependency_overrides[get_current_user] = _fake_get_current_user

    users_mod.service = fake_service

    if with_handlers:
        register_exception_handlers(app)

    return TestClient(app)

def test_ping_ok():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/users/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok" and data["router"] == "Users"

def test_list_users_admin_ok():
    admin = make_user(role=UserRole.ADMIN)
    user = make_user()
    client = make_app(fake_user=admin, fake_service=FakeService(user))
    resp = client.get("/api/v1/users/?page=1&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1 and len(data["items"]) == 1
    assert data["items"][0]["id"] == user.id

def test_list_users_forbidden_non_admin_returns_403():
    non_admin = make_user(role=UserRole.USER)
    client = make_app(fake_user=non_admin, fake_service=FakeForbiddenService(), with_handlers=True)
    resp = client.get("/api/v1/users/")
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("error", {}).get("code") == "FORBIDDEN"

def test_get_user_mapping_returns_dict():
    admin = make_user(role=UserRole.ADMIN)
    client = make_app(fake_user=admin, fake_service=FakeService())
    ids = [get_random_object_id(), get_random_object_id()]
    resp = client.get(f"/api/v1/users/mapping?ids={','.join(ids)}")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict) and set(data.keys()) == set(ids)

def test_create_update_delete_identity_and_role_flow():
    admin = make_user(role=UserRole.ADMIN)
    u = make_user()
    client = make_app(fake_user=admin, fake_service=FakeService(u))

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
    r1 = client.post("/api/v1/users/", json=payload)
    assert r1.status_code == 200 and r1.json()["username"] == "tester"

    r2 = client.patch(f"/api/v1/users/{u.id}", json={"settings": {"theme": "dark"}})
    assert r2.status_code == 200

    r3 = client.patch(f"/api/v1/users/{u.id}/role", json={"role": "admin", "permissions": ["p1"]})
    assert r3.status_code == 200 and r3.json()["role"] == "admin"

    r4 = client.patch(f"/api/v1/users/{u.id}/identity", json={"email": "new@example.com"})
    assert r4.status_code == 200 and r4.json()["email"] == "new@example.com"

    r5 = client.delete(f"/api/v1/users/{u.id}")
    assert r5.status_code == 200 and r5.json()["message"] == "用户删除成功"

def test_activate_reset_change_password_and_assets_endpoints():
    admin = make_user(role=UserRole.ADMIN)
    u = make_user()
    svc = FakeService(u)
    client = make_app(fake_user=admin, fake_service=svc)

    r1 = client.patch(f"/api/v1/users/{u.id}/activate", json=True)
    assert r1.status_code == 200 and r1.json()["is_active"] is True

    r2 = client.patch(f"/api/v1/users/{u.id}/password/reset", json={"new_password": "newpass"})
    assert r2.status_code == 200

    r3 = client.patch(f"/api/v1/users/{u.id}/password/change", json={"old_password": "newpass", "new_password": "newpass2"})
    assert r3.status_code == 200

    ids = [get_random_object_id(), get_random_object_id()]
    r4 = client.post("/api/v1/users/profiles/sign", json=ids)
    assert r4.status_code == 200 and all(s.startswith("signed://") for s in r4.json())

    files = {"file": ("profile.jpg", b"data", "image/jpeg")}
    r5 = client.post(f"/api/v1/users/{u.id}/profile", files=files)
    assert r5.status_code == 200 and r5.json()["ok"] is True
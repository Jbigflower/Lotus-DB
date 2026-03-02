import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.system import router as system_router
import src.routers.system as system_mod
from src.core.dependencies import get_current_user
from src.core.exceptions import ForbiddenError
from src.core.exceptions import register_exception_handlers
from src.models import (
    UserRead,
    UserRole,
    HealthCheckItem,
    SystemHealthStatus,
    SystemStatus,
    VersionInfo,
    ConfigCategory,
    ConfigPatchResult,
    LogFetchResponse,
    LogType,
    ResourceUsage,
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


class FakeService:
    async def health_check(self):
        return SystemHealthStatus(overall="ok", items=[HealthCheckItem(name="mongo", status="ok")])
    async def status_monitor(self):
        return SystemStatus(timestamp="t", app={"v": "1"}, db={"mongo": {"status": "ok"}})
    async def version_info(self):
        return VersionInfo(app_name="A", app_version="1", environment="dev")
    async def patch_config(self, data, current_user):
        if current_user.role != UserRole.ADMIN:
            raise ForbiddenError("无权限")
        return ConfigPatchResult(updated_keys=["APP__debug"], restart_required=True, preview={"debug": "true"})
    async def get_logs(self, data, current_user):
        if current_user.role != UserRole.ADMIN:
            raise ForbiddenError("无权限")
        return LogFetchResponse(log_type=data.type, lines=data.lines, content=[f"{data.type}-{i}" for i in range(1, data.lines + 1)])
    async def resource_usage(self, current_user):
        if current_user.role != UserRole.ADMIN:
            raise ForbiddenError("无权限")
        return ResourceUsage(timestamp="t", process={}, system={}, disk={})


def make_app(fake_user: UserRead, fake_service: FakeService) -> TestClient:
    app = FastAPI()
    app.include_router(system_router)
    # 覆盖认证依赖
    async def _fake_get_current_user():
        return fake_user
    app.dependency_overrides[get_current_user] = _fake_get_current_user
    # 替换模块级 service
    system_mod.service = fake_service
    # 注册全局异常处理器，确保 403/业务异常返回标准 JSON
    register_exception_handlers(app)
    return TestClient(app)


def test_ping_ok():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/system/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok" and data["router"] == "System"


def test_health_returns_schema():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall"] == "ok" and len(data["items"]) == 1


def test_status_returns_schema():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "app" in data and "db" in data


def test_version_returns_schema():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/system/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "A"


def test_patch_config_admin_ok():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    payload = {"category": "app", "updates": {"debug": "true"}}
    resp = client.patch("/api/v1/system/config", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated_keys"] == ["APP__debug"]


def test_get_logs_admin_ok():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/system/logs?type=app&lines=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["log_type"] == "app" and data["lines"] == 3 and len(data["content"]) == 3


def test_resources_admin_ok():
    client = make_app(fake_user=make_user(role=UserRole.ADMIN), fake_service=FakeService())
    resp = client.get("/api/v1/system/resources")
    assert resp.status_code == 200
    data = resp.json()
    assert "process" in data and "system" in data and "disk" in data


def test_patch_config_forbidden_returns_403():
    client = make_app(fake_user=make_user(role=UserRole.USER), fake_service=FakeService())
    payload = {"category": "app", "updates": {"debug": "true"}}
    resp = client.patch("/api/v1/system/config", json=payload)
    assert resp.status_code == 403
    body = resp.json()
    assert body.get("error", {}).get("code") == "FORBIDDEN"
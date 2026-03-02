import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.routers import register_routers
from src.core.exceptions import register_exception_handlers
from src.core.dependencies import get_current_user

import src.routers.system as system_mod
from src.services.system.system_service import SystemService
from src.logic.system.system_logic import SystemLogic
import src.logic.system.system_logic as logic_mod

from src.models import (
    UserRead,
    UserRole,
    HealthCheckItem,
    ConfigCategory,
    ConfigPatchResult,
    LogType,
)


def make_user(role=UserRole.ADMIN, uid="u1") -> UserRead:
    return UserRead(
        id=uid,
        username="admin",
        email="admin@example.com",
        role=role,
        permissions=[],
        is_active=True,
        is_verified=True,
        settings={},
        hashed_password=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class FakeRepo:
    async def check_mongo(self):
        return HealthCheckItem(name="mongo", status="ok")
    async def check_redis(self):
        return HealthCheckItem(name="redis", status="ok")
    async def check_chroma(self):
        return HealthCheckItem(name="chroma", status="ok")
    async def check_lance(self):
        return HealthCheckItem(name="lance", status="ok")
    async def fetch_logs(self, log_type: LogType, lines: int = 100):
        return [f"{log_type.value}-{i}" for i in range(1, lines + 1)]
    async def patch_env(self, category: ConfigCategory, updates: dict):
        return ConfigPatchResult(updated_keys=[f"{category.value.upper()}__debug"], restart_required=True, preview={"debug": "true"})


def make_app_with_fake_chain(fake_user_admin: UserRead, monkeypatch) -> TestClient:
    app = FastAPI()
    register_routers(app)
    register_exception_handlers(app)

    # 覆盖认证依赖
    async def _fake_get_current_user():
        return fake_user_admin
    app.dependency_overrides[get_current_user] = _fake_get_current_user

    # 使用真实 Service + Logic，但替换 Logic.repo
    svc = SystemService()
    svc.logic = SystemLogic()
    svc.logic.repo = FakeRepo()
    system_mod.service = svc

    # 限制 psutil 以避免环境差异
    class FakeMI:
        rss = 123456
    class FakeProc:
        def __init__(self, pid): pass
        def cpu_percent(self, interval=0.1): return 12.5
        def oneshot(self): return self
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def memory_percent(self): return 34.2
        def memory_info(self): return FakeMI()
    class FakeVM:
        total = 8000000000
        used = 3000000000
        percent = 37.5
    class FakePsutil:
        def Process(self, pid): return FakeProc(pid)
        def virtual_memory(self): return FakeVM()
        def cpu_percent(self, interval=0.1): return 56.0
    monkeypatch.setattr(logic_mod, "psutil", FakePsutil())

    return TestClient(app)


def test_system_endpoints_end_to_end(monkeypatch, tmp_path):
    client = make_app_with_fake_chain(make_user(UserRole.ADMIN), monkeypatch)

    # health
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    assert set([i["name"] for i in resp.json()["items"]]) == {"mongo", "redis", "chroma", "lance"}

    # status
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "app" in data and set(data["db"].keys()) == {"mongo", "redis", "chroma", "lance"}

    # version
    resp = client.get("/api/v1/system/version")
    assert resp.status_code == 200
    assert "app_version" in resp.json()

    # logs
    resp = client.get("/api/v1/system/logs?type=app&lines=3")
    assert resp.status_code == 200
    lj = resp.json()
    assert lj["log_type"] == "app" and lj["lines"] == 3 and len(lj["content"]) == 3

    # patch config
    resp = client.patch("/api/v1/system/config", json={"category": "app", "updates": {"debug": "true"}})
    assert resp.status_code == 200
    assert resp.json()["updated_keys"] == ["APP__debug"]

    # resources (已注入 FakePsutil)
    resp = client.get("/api/v1/system/resources")
    assert resp.status_code == 200
    rj = resp.json()
    assert rj["process"]["memory_bytes"] == 123456

    # 权限拒绝（将依赖覆盖为非管理员）
    app = client.app
    async def _user():
        return make_user(UserRole.USER)
    app.dependency_overrides[get_current_user] = _user
    resp = client.patch("/api/v1/system/config", json={"category": "app", "updates": {"debug": "true"}})
    assert resp.status_code == 403
    err = resp.json().get("error", {})
    assert err.get("code") == "FORBIDDEN"
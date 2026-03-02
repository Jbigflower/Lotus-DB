import pytest
from datetime import datetime, timezone

from src.services.system.system_service import SystemService
from src.core.exceptions import ForbiddenError
from src.models import (
    UserRead,
    UserRole,
    HealthCheckItem,
    SystemHealthStatus,
    SystemStatus,
    VersionInfo,
    LogType,
    ConfigCategory,
    ConfigPatchRequest,
    ConfigPatchResult,
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


class FakeLogic:
    async def health_check(self):
        return SystemHealthStatus(overall="ok", items=[HealthCheckItem(name="mongo", status="ok")])
    async def status_monitor(self):
        return SystemStatus(timestamp="t", app={"v": "1"}, db={"mongo": {"status": "ok"}})
    async def version_info(self):
        return VersionInfo(app_name="A", app_version="1", environment="dev")
    async def patch_config(self, data: ConfigPatchRequest):
        return ConfigPatchResult(updated_keys=["APP__debug"], restart_required=True, preview={"debug": "true"})
    async def get_logs(self, log_type: LogType, lines: int = 100):
        return [f"{log_type.value}-{i}" for i in range(1, lines + 1)]
    async def resource_usage(self):
        return ResourceUsage(
            timestamp="t",
            process={"cpu_percent": 1.0, "memory_percent": 2.0, "memory_bytes": 3},
            system={"cpu_percent": 10.0, "memory_total": 100, "memory_used": 20, "memory_percent": 20.0},
            disk={},
        )


@pytest.mark.asyncio
async def test_health_status_version_passthrough():
    svc = SystemService()
    svc.logic = FakeLogic()
    assert (await svc.health_check()).overall == "ok"
    assert "mongo" in (await svc.status_monitor()).db
    assert (await svc.version_info()).app_name == "A"


@pytest.mark.asyncio
async def test_patch_config_requires_admin_denied():
    svc = SystemService()
    svc.logic = FakeLogic()
    user = make_user(role=UserRole.USER)
    with pytest.raises(ForbiddenError):
        await svc.patch_config(ConfigPatchRequest(category=ConfigCategory.app, updates={"debug": "true"}), user)


@pytest.mark.asyncio
async def test_patch_config_admin_ok():
    svc = SystemService()
    svc.logic = FakeLogic()
    admin = make_user(role=UserRole.ADMIN)
    res = await svc.patch_config(ConfigPatchRequest(category=ConfigCategory.app, updates={"debug": "true"}), admin)
    assert res.updated_keys == ["APP__debug"]


@pytest.mark.asyncio
async def test_get_logs_wraps_response_and_requires_admin():
    svc = SystemService()
    svc.logic = FakeLogic()
    admin = make_user(role=UserRole.ADMIN)
    resp = await svc.get_logs(data=type("D", (), {"type": LogType.app, "lines": 3})(), current_user=admin)
    assert resp.log_type == LogType.app and resp.lines == 3 and len(resp.content) == 3

    user = make_user(role=UserRole.USER)
    with pytest.raises(ForbiddenError):
        await svc.get_logs(data=type("D", (), {"type": LogType.app, "lines": 3})(), current_user=user)


@pytest.mark.asyncio
async def test_resource_usage_requires_admin():
    svc = SystemService()
    svc.logic = FakeLogic()
    user = make_user(role=UserRole.USER)
    with pytest.raises(ForbiddenError):
        await svc.resource_usage(user)
    admin = make_user(role=UserRole.ADMIN)
    ru = await svc.resource_usage(admin)
    assert ru.process.memory_bytes == 3
import pytest
from datetime import datetime, timezone
from pathlib import Path

from src.logic.system.system_logic import SystemLogic
import src.logic.system.system_logic as logic_mod
from src.models import (
    HealthCheckItem,
    SystemHealthStatus,
    SystemStatus,
    VersionInfo,
    LogType,
    ConfigCategory,
    ConfigPatchRequest,
    ConfigPatchResult,
)


class FakeRepo:
    async def check_mongo(self):
        return HealthCheckItem(name="mongo", status="ok", latency_ms=1.0, details={"ok": "1"})
    async def check_redis(self):
        return HealthCheckItem(name="redis", status="ok", latency_ms=1.0, details={"clients": "5"})
    async def check_chroma(self):
        return HealthCheckItem(name="chroma", status="ok", latency_ms=1.0, details={"version": "1.2.3"})
    async def check_lance(self):
        return HealthCheckItem(name="lance", status="ok", latency_ms=1.0, details={"tables": "2"})
    async def fetch_logs(self, log_type: LogType, lines: int = 100):
        return [f"{log_type.value}-l{i}" for i in range(1, lines + 1)]
    async def patch_env(self, category: ConfigCategory, updates: dict):
        return ConfigPatchResult(updated_keys=[f"{category.value.upper()}__{k}" for k in updates.keys()],
                                 restart_required=True, preview=updates)


@pytest.mark.asyncio
async def test_health_check_aggregates_ok():
    logic = SystemLogic()
    logic.repo = FakeRepo()
    status = await logic.health_check()
    assert isinstance(status, SystemHealthStatus)
    assert status.overall == "ok" and len(status.items) == 4
    assert {i.name for i in status.items} == {"mongo", "redis", "chroma", "lance"}


@pytest.mark.asyncio
async def test_status_monitor_builds_db_map():
    logic = SystemLogic()
    logic.repo = FakeRepo()
    st = await logic.status_monitor()
    assert isinstance(st, SystemStatus)
    assert set(st.db.keys()) == {"mongo", "redis", "chroma", "lance"}
    assert "app" in st.model_dump()


@pytest.mark.asyncio
async def test_version_info_returns_settings():
    logic = SystemLogic()
    vi = await logic.version_info()
    assert isinstance(vi, VersionInfo)
    assert vi.app_name and vi.app_version and vi.environment


@pytest.mark.asyncio
async def test_patch_config_delegates_to_repo():
    logic = SystemLogic()
    logic.repo = FakeRepo()
    req = ConfigPatchRequest(category=ConfigCategory.app, updates={"debug": "true"})
    res = await logic.patch_config(req)
    assert isinstance(res, ConfigPatchResult)
    assert res.updated_keys == ["APP__debug"]


@pytest.mark.asyncio
async def test_get_logs_delegates_to_repo():
    logic = SystemLogic()
    logic.repo = FakeRepo()
    lines = await logic.get_logs(LogType.app, 3)
    assert lines == ["app-l1", "app-l2", "app-l3"]


@pytest.mark.asyncio
async def test_resource_usage_collects_data(monkeypatch, tmp_path):
    # Fake psutil
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

    # Prepare directories
    from config.setting import settings
    library = tmp_path / "lib"
    user = tmp_path / "user"
    other = tmp_path / "other"
    for p in [library, user, other]:
        p.mkdir()
        (p / "f1.txt").write_text("x", encoding="utf-8")

    settings.media.library_prefix = str(library)
    settings.media.user_prefix = str(user)
    settings.media.other_prefix = str(other)

    logic = SystemLogic()
    usage = await logic.resource_usage()
    assert usage.process.memory_bytes == 123456
    assert usage.system.memory_total == 8000000000
    assert usage.disk["library"].exists and usage.disk["user"].exists and usage.disk["other"].exists
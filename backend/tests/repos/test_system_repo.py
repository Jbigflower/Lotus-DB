import pytest
from pathlib import Path

from src.repos.system.system_repo import SystemRepo
import src.repos.system.system_repo as repo_mod
from src.models import HealthCheckItem, LogType, ConfigCategory


@pytest.mark.asyncio
async def test_check_mongo_success(monkeypatch):
    class FakeMongoMgr:
        async def ping(self):
            return True
        async def get_stats(self):
            return {"ok": 1, "collections": 5}

    async def noop():
        return None

    monkeypatch.setattr(repo_mod, "init_mongo", noop)
    monkeypatch.setattr(repo_mod, "get_mongo_manager", lambda: FakeMongoMgr())

    repo = SystemRepo()
    item = await repo.check_mongo()
    assert isinstance(item, HealthCheckItem)
    assert item.name == "mongo" and item.status == "ok"
    assert item.details and item.details.get("ok") == "1"


@pytest.mark.asyncio
async def test_check_mongo_error(monkeypatch):
    async def boom():
        raise RuntimeError("mongo down")
    monkeypatch.setattr(repo_mod, "init_mongo", boom)

    repo = SystemRepo()
    item = await repo.check_mongo()
    assert item.name == "mongo" and item.status == "error"
    assert "mongo down" in (item.message or "")


@pytest.mark.asyncio
async def test_check_redis_success(monkeypatch):
    class FakeRedisMgr:
        async def ping(self):
            return True
        async def get_info(self):
            return {"connected_clients": 10}

    async def noop():
        return None

    monkeypatch.setattr(repo_mod, "init_redis", noop)
    monkeypatch.setattr(repo_mod, "get_redis_manager", lambda: FakeRedisMgr())

    repo = SystemRepo()
    item = await repo.check_redis()
    assert item.name == "redis" and item.status == "ok"
    assert item.details and item.details.get("connected_clients") == "10"


@pytest.mark.asyncio
async def test_check_chroma_success(monkeypatch):
    class FakeClient:
        def get_version(self):
            return "1.2.3"
    class FakeChromaMgr:
        is_connected = True
        client = FakeClient()

    async def noop():
        return None

    monkeypatch.setattr(repo_mod, "init_chroma", noop)
    monkeypatch.setattr(repo_mod, "get_chroma_manager", lambda: FakeChromaMgr())

    repo = SystemRepo()
    item = await repo.check_chroma()
    assert item.name == "chroma" and item.status == "ok"
    assert item.details and item.details.get("version") == "1.2.3"


@pytest.mark.asyncio
async def test_check_lance_success(monkeypatch):
    class FakeLanceMgr:
        is_connected = True
        async def list_tables(self):
            return ["t1", "t2"]

    async def noop():
        return None

    monkeypatch.setattr(repo_mod, "init_lance", noop)
    monkeypatch.setattr(repo_mod, "get_lance_manager", lambda: FakeLanceMgr())

    repo = SystemRepo()
    item = await repo.check_lance()
    assert item.name == "lance" and item.status == "ok"
    assert item.details and item.details.get("tables") == "2"


@pytest.mark.asyncio
async def test_fetch_logs_tail_returns_last_n_lines(monkeypatch, tmp_path):
    # 在临时目录下创建 logs/app.log
    monkeypatch.chdir(tmp_path)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    app_log = logs_dir / "app.log"
    app_log.write_text("l1\nl2\nl3\nl4\n", encoding="utf-8")

    repo = SystemRepo()
    lines = await repo.fetch_logs(LogType.app, lines=2)
    assert lines == ["l3", "l4"]


@pytest.mark.asyncio
async def test_patch_env_writes_updates(monkeypatch, tmp_path):
    # 使用 tmp_path 下的 .env
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXIST=1\n# comment here\n", encoding="utf-8")

    repo = SystemRepo()
    result = await repo.patch_env(ConfigCategory.app, {"debug": "false", "app_name": "Lotus"})
    assert result.restart_required is True
    assert set(result.updated_keys) == {"APP__debug", "APP__app_name"}
    assert result.preview == {"APP__debug": "false", "APP__app_name": "Lotus"}

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "EXIST=1" in content
    assert "APP__debug=false" in content and "APP__app_name=Lotus" in content
from typing import Dict, List, Tuple
import asyncio
import time
from pathlib import Path

from src.core.handler import repo_handler
from config.logging import get_logger
from src.db import (
    init_mongo,
    get_mongo_manager,
    init_redis,
    get_redis_manager,
    init_chroma,
    get_chroma_manager,
    init_lance,
    get_lance_manager,
)
from src.models import HealthCheckItem, LogType, ConfigCategory, ConfigPatchResult

logger = get_logger(__name__)


class SystemRepo:
    """系统仓储：健康检查、日志访问、配置写入"""

    @repo_handler("Mongo 健康检查")
    async def check_mongo(self) -> HealthCheckItem:
        start = time.perf_counter()
        try:
            await init_mongo()
            ok = await get_mongo_manager().ping()
            stats = await get_mongo_manager().get_stats()
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="mongo",
                status="ok" if ok else "error",
                latency_ms=latency,
                details={k: str(v) for k, v in stats.items()},
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="mongo", status="error", latency_ms=latency, message=str(e)
            )

    @repo_handler("Redis 健康检查")
    async def check_redis(self) -> HealthCheckItem:
        start = time.perf_counter()
        try:
            await init_redis()
            ok = await get_redis_manager().ping()
            info = await get_redis_manager().get_info()
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="redis",
                status="ok" if ok else "error",
                latency_ms=latency,
                details={k: str(v) for k, v in info.items()},
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="redis", status="error", latency_ms=latency, message=str(e)
            )

    @repo_handler("Chroma 健康检查")
    async def check_chroma(self) -> HealthCheckItem:
        start = time.perf_counter()
        try:
            await init_chroma()
            mgr = get_chroma_manager()
            version = ""
            try:
                version = mgr.client.get_version()
            except Exception:
                pass
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="chroma",
                status="ok" if mgr.is_connected else "error",
                latency_ms=latency,
                details={"version": str(version)},
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="chroma", status="error", latency_ms=latency, message=str(e)
            )

    @repo_handler("LanceDB 健康检查")
    async def check_lance(self) -> HealthCheckItem:
        start = time.perf_counter()
        try:
            await init_lance()
            mgr = get_lance_manager()
            tables: List[str] = []
            try:
                tables = await mgr.list_tables()
            except Exception:
                pass
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="lance",
                status="ok" if mgr.is_connected else "error",
                latency_ms=latency,
                details={"tables": str(len(tables))},
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return HealthCheckItem(
                name="lance", status="error", latency_ms=latency, message=str(e)
            )

    @repo_handler("读取日志")
    async def fetch_logs(self, log_type: LogType, lines: int = 100) -> List[str]:
        mapping = {
            LogType.app: Path("logs/app.log"),
            LogType.error: Path("logs/error.log"),
            LogType.performance: Path("logs/performance.log"),
            LogType.worker_all: Path("logs/worker_all.log"),
            LogType.worker_error: Path("logs/worker_error.log"),
        }
        path = mapping.get(log_type)
        if not path or not path.exists():
            return []

        async def _tail(p: Path, n: int) -> List[str]:
            def _read_tail() -> List[str]:
                try:
                    with p.open("r", encoding="utf-8", errors="ignore") as f:
                        content = f.readlines()
                        return [line.rstrip("\n") for line in content[-n:]]
                except Exception:
                    return []

            return await asyncio.to_thread(_read_tail)

        return await _tail(path, lines)

    @repo_handler("修改 .env 配置")
    async def patch_env(
        self, category: ConfigCategory, updates: Dict[str, str]
    ) -> ConfigPatchResult:
        env_path = Path(".env")
        existing_lines: List[str] = []
        if env_path.exists():
            existing_lines = env_path.read_text(encoding="utf-8").splitlines()

        # 将 .env 转为字典（简易解析，不处理复杂引用）
        kv: Dict[str, str] = {}
        for line in existing_lines:
            if not line or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()

        # 采用 pydantic-settings 的默认嵌套分隔符 __
        prefix = category.value.upper() + "__"
        updated_keys: List[str] = []
        for k, v in updates.items():
            env_key = f"{prefix}{k}"
            kv[env_key] = str(v)
            updated_keys.append(env_key)

        # 重新写回 .env（保留原有注释行）
        new_lines: List[str] = []
        seen = set()
        for line in existing_lines:
            if not line or line.strip().startswith("#") or "=" not in line:
                new_lines.append(line)
                continue
            k, _ = line.split("=", 1)
            k = k.strip()
            if k in kv:
                new_lines.append(f"{k}={kv[k]}")
                seen.add(k)
            else:
                new_lines.append(line)
        # 追加新增键
        for k, v in kv.items():
            if k not in seen:
                new_lines.append(f"{k}={v}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        return ConfigPatchResult(
            updated_keys=updated_keys,
            restart_required=True,
            preview={k: updates[k.split("__")[-1]] for k in updated_keys},
        )

from datetime import datetime, timezone
import asyncio
import os
from pathlib import Path
try:
    import psutil  # type: ignore
except Exception:
    psutil = None
from src.core.handler import logic_handler
from config.logging import get_logic_logger
from config.setting import settings
from src.models import (
    SystemHealthStatus,
    HealthCheckItem,
    SystemStatus,
    VersionInfo,
    LogType,
    ConfigPatchRequest,
    ConfigPatchResult,
    ResourceUsage,
    FolderUsage,
    ProcessUsage,
    SystemUsage,
    UserActivity,
    UserActivityList,
)
from src.repos.system.system_repo import SystemRepo
from src.repos import UserRepo, UserRedisRepo

logger = get_logic_logger("system_logic")

class SystemLogic:
    def __init__(self) -> None:
        self.repo = SystemRepo()
        self.user_repo = UserRepo()
        self.user_redis = UserRedisRepo()

    @logic_handler("健康检查")
    async def health_check(self) -> SystemHealthStatus:
        items = await asyncio.gather(
            self.repo.check_mongo(),
            self.repo.check_redis(),
            self.repo.check_chroma(),
            self.repo.check_lance(),
        )
        # 计算总体状态
        if all(i.status == "ok" for i in items):
            overall = "ok"
        elif any(i.status == "error" for i in items):
            overall = "error"
        else:
            overall = "degraded"
        return SystemHealthStatus(overall=overall, items=list(items))

    @logic_handler("状态监控")
    async def status_monitor(self) -> SystemStatus:
        # 复用健康检查项的 details 作为状态数据来源
        health = await self.health_check()
        db: dict = {}
        for item in health.items:
            db[item.name] = {
                "status": item.status,
                "latency_ms": item.latency_ms,
                "details": item.details,
            }
        app = {
            "name": settings.app.app_name,
            "version": settings.app.app_version,
            "environment": settings.app.environment,
            "debug": str(settings.app.debug),
        }
        return SystemStatus(
            timestamp=datetime.now(timezone.utc).isoformat(),
            app=app,
            db=db,
        )

    @logic_handler("版本查看")
    async def version_info(self) -> VersionInfo:
        return VersionInfo(
            app_name=settings.app.app_name,
            app_version=settings.app.app_version,
            environment=settings.app.environment,
        )

    @logic_handler("配置修改")
    async def patch_config(self, data: ConfigPatchRequest) -> ConfigPatchResult:
        result = await self.repo.patch_env(data.category, data.updates)
        # 说明：运行时热更新未实现，需重启以生效
        return result

    @logic_handler("日志获取")
    async def get_logs(self, log_type: LogType, lines: int = 100) -> list[str]:
        return await self.repo.fetch_logs(log_type, lines)

    @logic_handler("服务资源占用")
    async def resource_usage(self) -> ResourceUsage:
        timestamp = datetime.now(timezone.utc).isoformat()

        cpu_p = None
        mem_p = None
        mem_b = None
        sys_cpu = None
        sys_mem_total = None
        sys_mem_used = None
        sys_mem_percent = None

        if psutil:
            proc = psutil.Process(os.getpid())
            cpu_p = proc.cpu_percent(interval=0.1)
            with proc.oneshot():
                mem_p = proc.memory_percent()
                mem_b = proc.memory_info().rss
            vm = psutil.virtual_memory()
            sys_cpu = psutil.cpu_percent(interval=0.1)
            sys_mem_total = vm.total
            sys_mem_used = vm.used
            sys_mem_percent = vm.percent

        process_usage = ProcessUsage(
            cpu_percent=cpu_p, memory_percent=mem_p, memory_bytes=mem_b
        )
        system_usage = SystemUsage(
            cpu_percent=sys_cpu,
            memory_total=sys_mem_total,
            memory_used=sys_mem_used,
            memory_percent=sys_mem_percent,
        )

        async def calc_folder(label: str, path_str: str):
            p = Path(path_str)
            if not p.exists():
                return label, FolderUsage(path=str(p), exists=False)
            def walker():
                total = 0
                files = 0
                dirs = 0
                for root, dirnames, filenames in os.walk(p, followlinks=False):
                    dirs += len(dirnames)
                    for fname in filenames:
                        fp = os.path.join(root, fname)
                        try:
                            total += os.path.getsize(fp)
                            files += 1
                        except Exception:
                            pass
                return FolderUsage(
                    path=str(p),
                    exists=True,
                    size_bytes=total,
                    file_count=files,
                    dir_count=dirs,
                )
            fu = await asyncio.to_thread(walker)
            return label, fu

        paths = {
            "library": settings.media.library_prefix,
            "user": settings.media.user_prefix,
            "other": settings.media.other_prefix,
        }
        results = await asyncio.gather(
            *(calc_folder(k, v) for k, v in paths.items())
        )
        disk_usage = {k: v for k, v in results}

        return ResourceUsage(
            timestamp=timestamp,
            process=process_usage,
            system=system_usage,
            disk=disk_usage,
        )

    @logic_handler("获取用户活动")
    async def get_user_activities(self) -> UserActivityList:
        users = await self.user_repo.find(filter_query={}, limit=1000)
        activities = []
        for user in users:
            sessions = await self.user_redis.list_device_sessions(user.id)
            for s in sessions:
                # 构造设备显示名称
                alias = s.get("alias")
                ua = s.get("user_agent") or "未知"
                platform = s.get("platform") or ""
                device_name = f"{alias or ua} · {platform}" if platform else (alias or ua)

                activities.append(UserActivity(
                    username=user.username,
                    session_id=s.get("session_id"),
                    ip=s.get("ip"),
                    location=s.get("location"),
                    device=device_name,
                    platform=s.get("platform"),
                    login_at=s.get("created_at"),
                    last_active_at=s.get("last_active_at")
                ))
        # 按最后活跃时间倒序
        activities.sort(key=lambda x: x.last_active_at or "", reverse=True)
        return UserActivityList(items=activities)

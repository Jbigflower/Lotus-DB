import asyncio
import time
from typing import Dict, List, Optional

from src.async_worker.core import TaskPriority, send_task
from config.logging import get_beat_logger


class Beat:
    """
    简易定时任务调度器（类 Celery beat）
    - 周期性将任务投递到 Redis 队列，由 Worker 消费执行
    - 与 Worker 解耦，仅负责投递
    """

    def __init__(self, entries: List[Dict], tick_interval: float = 1.0):
        # entries: [{"name": str, "interval": int|float, "priority": TaskPriority, "payload": Optional[dict]}]
        self.entries = entries
        self.tick_interval = tick_interval
        self._shutdown = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

        # 初始化下一次触发时间
        now = time.time()
        for e in self.entries:
            e["_next"] = now + float(e["interval"])

    async def start(self) -> None:
        # 异步单例启动调度器
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            get_beat_logger("scheduler").info("[Beat] Started")

    async def shutdown(self) -> None:
        self._shutdown.set()
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        get_beat_logger("scheduler").info("[Beat] Shutdown complete")

    async def _loop(self) -> None:
        # 调度器的核心逻辑
        logger = get_beat_logger("scheduler")
        while not self._shutdown.is_set():
            now = time.time()
            for e in self.entries:
                nxt = e.get("_next", now)
                if now >= nxt:
                    try:
                        await send_task(
                            task_name=e["name"],
                            payload=e.get("payload"),
                            priority=e.get("priority", TaskPriority.HIGH),
                        )
                        logger.info(
                            "[Beat] 投递任务",
                            extra={"task": e["name"], "interval": e["interval"]},
                        )
                    except Exception as ex:
                        logger.error(
                            f"[Beat] send_task error: {ex}",
                            extra={"error": str(ex), "error_type": type(ex).__name__},
                            exc_info=True,
                        )
                    finally:
                        e["_next"] = now + float(e["interval"])
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=self.tick_interval
                )
            except asyncio.TimeoutError:
                pass

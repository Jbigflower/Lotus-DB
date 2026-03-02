import asyncio
import os
import signal
from multiprocessing import Process
from typing import Optional

from src.async_worker.context import init_resources, close_resources
from config.logging import get_worker_logger
from src.async_worker.core import Worker
from src.async_worker.register import TASK_REGISTRY, SCHEDULED_TASKS
from src.async_worker.scheduler import Beat


async def worker_entrypoint() -> None:
    """
    Worker 后台进程入口（异步）
    - 初始化共享资源（DB、Redis）
    - 启动任务消费者与定时投递器
    - 持续运行直到接收退出信号
    """
    await init_resources()
    get_worker_logger("process").info("[WorkerEntry] 资源初始化完成")

    # 并发度可配置
    concurrency = int(os.getenv("WORKER_CONCURRENCY", "5"))
    worker = Worker(registry=TASK_REGISTRY, concurrency=concurrency)
    await worker.start()

    beat = Beat(entries=SCHEDULED_TASKS, tick_interval=1.0)
    await beat.start()

    stop_event = asyncio.Event()

    def _signal_stop():
        stop_event.set()

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _signal_stop)
        loop.add_signal_handler(signal.SIGTERM, _signal_stop)
    except NotImplementedError:
        # Windows 等平台可能不支持；用 sleep 循环兜底
        pass

    try:
        await stop_event.wait()
    finally:
        await beat.shutdown()
        await worker.shutdown()
        await close_resources()
        get_worker_logger("process").info("[WorkerEntry] 已关闭资源")


def run_worker_forever() -> None:
    """
    进程启动包装（同步），用于作为独立后台进程运行。
    """
    asyncio.run(worker_entrypoint())


_worker_process: Optional[Process] = None


def start_background_worker() -> Process:
    """
    从 FastAPI 主进程调用此函数，启动后台 Worker 进程。
    - 该进程设置 daemon=True，当主进程退出时自动停止（生命周期同步）。
    """
    global _worker_process
    if _worker_process and _worker_process.is_alive():
        return _worker_process

    proc = Process(target=run_worker_forever, name="lotus-worker", daemon=True)
    proc.start()
    _worker_process = proc
    get_worker_logger("process").info(
        "[WorkerProcess] started", extra={"pid": proc.pid}
    )
    return proc


def stop_background_worker(proc: Optional[Process] = None) -> None:
    """
    在 FastAPI 关闭时调用，停止后台 Worker 进程。
    """
    global _worker_process
    p = proc or _worker_process
    if p and p.is_alive():
        p.terminate()
        p.join(timeout=10)
        get_worker_logger("process").info(
            "[WorkerProcess] terminated", extra={"pid": p.pid}
        )
    _worker_process = None


if __name__ == "__main__":
    # 允许独立启动：python -m src.async_worker.main
    run_worker_forever()

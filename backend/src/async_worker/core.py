# imports section
import asyncio
import json
import os
import socket
import time
from enum import IntEnum, Enum
from datetime import datetime, date
from typing import Any, Awaitable, Callable, Dict, Optional
from pydantic import BaseModel
import inspect
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from src.db.redis_db import get_redis_client
from src.models import TaskPriority
from config.logging import get_worker_logger, set_trace_id, clear_trace_id, get_trace_id

# Redis Streams 相关配置
TASK_STREAM_KEY = os.getenv("LOTUS_TASK_STREAM", "lotus:task-stream")  # 队列标识
TASK_GROUP = os.getenv(
    "LOTUS_TASK_GROUP", "lotus-worker"
)  # 消费组名称，多 Worker 协同消费，避免重复处理任务
STREAM_MAX_LEN = int(
    os.getenv("LOTUS_STREAM_MAX_LEN", "10000")
)  # 避免任务堆积过多导致 Redis 内存溢出
BLOCK_MS = int(os.getenv("LOTUS_BLOCK_MS", "1000"))  # 消费阻塞等待时间
CLAIM_IDLE_MS = int(
    os.getenv("LOTUS_CLAIM_IDLE_MS", "60000")
)  # 自动认领的空闲阈值（毫秒）
RETRY_DELAY_SEC = int(os.getenv("LOTUS_RETRY_DELAY_SEC", "5"))  # 失败重试延迟（秒）

producer_logger = get_worker_logger("producer")


async def ensure_stream_and_group(redis: Redis) -> None:
    """
    确保 Stream 和 Group 存在；若不存在则创建（MKSTREAM）。
    """
    try:
        # 为指定的 Stream 队列创建消费组
        await redis.xgroup_create(TASK_STREAM_KEY, TASK_GROUP, id="0", mkstream=True)
    except ResponseError as e:
        # 已存在则忽略
        if "BUSYGROUP" in str(e):
            return
        raise


async def send_task(
    task_name: str,
    payload: Optional[Dict[str, Any]] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 3,
) -> str:
    """
    标准化任务发布接口（生产者）
    - 保持现有 service 代码最小改动：直接调用该函数即可。
    - 返回消息 ID。
    """
    redis = await get_redis_client()
    # 1) 尝试创建 group（如果尚未创建）
    try:
        await ensure_stream_and_group(redis)
    except Exception:
        # 非致命，send_task 可继续
        pass

    message = {
        "task": task_name,
        "payload": json.dumps(payload or {}, default=_json_default, ensure_ascii=False),
        "priority": str(int(priority)),
        "ts": str(time.time()),
        "retries": "0",
        "max_retries": str(max_retries),
    }
    # 2) 异步发布任务到消息队列
    msg_id = await redis.xadd(
        TASK_STREAM_KEY,
        message,
        maxlen=STREAM_MAX_LEN,
        approximate=True,
    )
    # 任务发布日志

    producer_logger.info(
        f"[Producer] 发布任务 {task_name}",
        extra={
            "trace_id": get_trace_id(),
            "task_name": task_name,
            "msg_id": msg_id,
            "priority": str(priority),
            "max_retries": max_retries,
        },
    )
    return msg_id


def send_task_sync(
    task_name: str,
    payload: Optional[Dict[str, Any]] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 3,
) -> str:
    """
    同步环境发布任务（包装器），可在非 async 场景中使用。基本上不使用
    """
    # 1) 获取当前线程的事件循环
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    # 2) 如果事件循环存在且正在运行，将任务委托给异步函数
    if loop and loop.is_running():
        future = asyncio.ensure_future(
            send_task(task_name, payload, priority, max_retries)
        )
        # 这里返回空字符串；如果需要返回 ID，可在调用方 await
        return ""
    # 3) 如果事件循环不存在或未运行，直接运行异步任务
    else:
        return asyncio.run(send_task(task_name, payload, priority, max_retries))


async def _invoke_task(
    func: Callable[..., Awaitable[Any]] | Callable[..., Any],
    payload: dict | None = None,
) -> Any:
    """
    智能调用函数：
    - 如果函数无参数：直接调用。
    - 如果函数参数可匹配 payload：按 kwargs 传递。
    - 如果仅接受单参数：传递 payload。
    - 支持同步/异步函数。
    """
    payload = payload or {}
    sig = inspect.signature(func)
    params = sig.parameters

    # 无参数函数
    if not params:
        if inspect.iscoroutinefunction(func):
            return await func()
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func)

    # 分析参数结构
    param_names = [
        name
        for name, p in params.items()
        if p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    required_names = [
        name
        for name, p in params.items()
        if p.default is inspect.Parameter.empty
        and p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

    # 尝试 kwargs 调用
    kwargs = {k: payload[k] for k in param_names if k in payload}
    can_use_kwargs = has_var_kw or all(name in kwargs for name in required_names)

    try:
        if can_use_kwargs:
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            else:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, lambda: func(**kwargs))
        else:
            # 如果函数只有一个参数，直接传 payload 本身
            if len(params) == 1:
                if inspect.iscoroutinefunction(func):
                    return await func(payload)
                else:
                    loop = asyncio.get_running_loop()
                    return await loop.run_in_executor(None, lambda: func(payload))
            else:
                # 参数不匹配时抛出异常
                raise TypeError(
                    f"Cannot match payload {payload} to function {func.__name__} parameters: {list(params.keys())}"
                )
    except Exception as e:
        # 明确报错
        raise RuntimeError(f"Task invocation failed for {func.__name__}: {e}") from e


class Worker:
    """
    Redis Streams 消费者（后台进程核心）
    - 持续监听任务队列
    - 自动获取并执行队列中的任务
    - 调用对应的任务处理函数完成任务
    #TODO 任务优先级调度 && CPU密集任务剥离
    """

    def __init__(
        self,
        registry: Dict[str, Callable[..., Any]],
        concurrency: int = 10,
        consumer_name: Optional[str] = None,
    ):
        self.registry = registry
        self.concurrency = concurrency
        self.consumer_name = consumer_name or f"{socket.gethostname()}-{os.getpid()}"
        self._shutdown = asyncio.Event()
        self._loop_task: Optional[asyncio.Task] = None
        self._redis: Optional[Redis] = None
        self.logger = get_worker_logger("core")

    async def start(self) -> None:
        self._redis = await get_redis_client()
        await ensure_stream_and_group(self._redis)
        self._loop_task = asyncio.create_task(self._run_loop())
        self.logger.info(
            "[Worker] Started",
            extra={
                "trace_id": get_trace_id(),
                "consumer": self.consumer_name,
                "concurrency": self.concurrency,
            },
        )

    async def shutdown(self) -> None:
        self._shutdown.set()
        if self._loop_task:
            try:
                self._loop_task.cancel()
                await asyncio.gather(self._loop_task, return_exceptions=True)
            except asyncio.CancelledError:
                pass
        self.logger.info(
            "[Worker] Shutdown complete", extra={"trace_id": get_trace_id()}
        )

    async def _claim_stale(self) -> None:
        """
        自动认领超时未处理的消息，避免长时间挂起。
        """
        if not self._redis:
            return
        try:
            # xautoclaim Redis自动认领“闲置超时”的任务 返回 (next_id, messages)
            _, messages = await self._redis.xautoclaim(
                TASK_STREAM_KEY,
                TASK_GROUP,
                self.consumer_name,
                min_idle_time=CLAIM_IDLE_MS,
                start_id="0-0",
                count=self.concurrency,
            )
            # 认领后由当前消费者继续处理，不需要额外操作
        except ResponseError:
            # Redis < 6.2 无 xautoclaim，可忽略或实现 XPENDING+XCLAIM 兜底
            pass
        except Exception:
            pass

    async def _run_loop(self) -> None:
        # Worker 的 “心脏”，持续执行 “认领超时任务 → 读取新任务 → 并发处理” 的逻辑
        assert self._redis is not None
        while not self._shutdown.is_set():
            await self._claim_stale()
            try:
                results = await self._redis.xreadgroup(
                    groupname=TASK_GROUP,
                    consumername=self.consumer_name,
                    streams={TASK_STREAM_KEY: ">"},
                    count=self.concurrency,
                    block=BLOCK_MS,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    f"[Worker] xreadgroup error: {e}",
                    extra={
                        "trace_id": get_trace_id(),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                await asyncio.sleep(1)
                continue

            if not results:
                continue

            run_tasks: list[asyncio.Task] = []
            for _, messages in results:
                for msg_id, fields in messages:
                    msg_id_str = _to_str(msg_id)
                    fields_decoded = _decode_kv(fields)
                    run_tasks.append(
                        asyncio.create_task(
                            self._execute_and_ack(msg_id_str, fields_decoded)
                        )
                    )

            if run_tasks:
                await asyncio.gather(*run_tasks, return_exceptions=True)

    async def _execute_and_ack(self, msg_id: str, fields: Dict[str, str]) -> None:
        assert self._redis is not None
        logger = self.logger
        # 将 Redis 消息 ID 作为 trace_id 贯穿任务执行链路
        set_trace_id(msg_id)
        start_ts = time.time()
        try:
            name = fields.get("task")
            payload_raw = fields.get("payload") or "{}"
            retries = int(fields.get("retries", "0"))
            max_retries = int(fields.get("max_retries", "3"))

            if not name:
                await self._redis.xack(TASK_STREAM_KEY, TASK_GROUP, msg_id)
                await self._redis.xdel(TASK_STREAM_KEY, msg_id)
                logger.warning(
                    "[Worker] 空任务消息，直接确认并删除",
                    extra={"trace_id": msg_id, "msg_id": msg_id},
                )
                return

            func = self.registry.get(name)
            if not func:
                logger.error(
                    "[Worker] 未知任务(drop)",
                    extra={"trace_id": msg_id, "task": name, "msg_id": msg_id},
                )
                await self._redis.xack(TASK_STREAM_KEY, TASK_GROUP, msg_id)
                await self._redis.xdel(TASK_STREAM_KEY, msg_id)
                return

            payload = json.loads(payload_raw)
            logger.info(
                f"[Worker] 执行任务 {name}",
                extra={
                    "trace_id": msg_id,
                    "msg_id": msg_id,
                    "task": name,
                    "retries": retries,
                    "max_retries": max_retries,
                },
            )

            result = await _invoke_task(func, payload)

            await self._redis.xack(TASK_STREAM_KEY, TASK_GROUP, msg_id)
            await self._redis.xdel(TASK_STREAM_KEY, msg_id)

            elapsed = time.time() - start_ts
            # 简要结果摘要
            if isinstance(result, dict):
                summary = f"keys={len(result)}"
            elif isinstance(result, list):
                summary = f"len={len(result)}"
            elif result is None:
                summary = "none"
            else:
                summary = str(type(result))

            logger.info(
                f"[Worker] 任务完成 {name} | 耗时 {elapsed:.3f}s",
                extra={
                    "trace_id": msg_id,
                    "msg_id": msg_id,
                    "task": name,
                    "result": summary,
                    "execution_time": elapsed,
                    "status": "success",
                },
            )
        except Exception as e:
            logger.error(
                f"[Worker] 任务失败: {e}",
                extra={
                    "trace_id": msg_id,
                    "msg_id": msg_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "status": "error",
                },
                exc_info=True,
            )
            try:
                await self._redis.xack(TASK_STREAM_KEY, TASK_GROUP, msg_id)
                if retries < max_retries:
                    await asyncio.sleep(RETRY_DELAY_SEC)
                    await self._redis.xadd(
                        TASK_STREAM_KEY,
                        {
                            "task": fields.get("task", ""),
                            "payload": fields.get("payload", "{}"),
                            "priority": fields.get(
                                "priority", str(int(TaskPriority.NORMAL))
                            ),
                            "ts": str(time.time()),
                            "retries": str(retries + 1),
                            "max_retries": str(max_retries),
                        },
                        maxlen=STREAM_MAX_LEN,
                        approximate=True,
                    )
                    logger.warning(
                        "[Worker] 已计划重试",
                        extra={
                            "trace_id": msg_id,
                            "msg_id": msg_id,
                            "task": fields.get("task", ""),
                            "next_retries": retries + 1,
                        },
                    )
                else:
                    await self._redis.xdel(TASK_STREAM_KEY, msg_id)
                    logger.error(
                        "[Worker] 超过最大重试次数，已删除消息",
                        extra={
                            "trace_id": msg_id,
                            "msg_id": msg_id,
                            "task": fields.get("task", ""),
                            "max_retries": max_retries,
                        },
                    )
            except Exception as ack_e:
                logger.error(
                    f"[Worker] Ack/Retry 出错: {ack_e}",
                    extra={
                        "trace_id": msg_id,
                        "msg_id": msg_id,
                        "error": str(ack_e),
                        "error_type": type(ack_e).__name__,
                    },
                    exc_info=True,
                )
        finally:
            clear_trace_id()


# helper functions (bytes → str decode)
def _to_str(x):
    return x.decode() if isinstance(x, (bytes, bytearray)) else x


def _decode_kv(d: Dict[Any, Any]) -> Dict[str, str]:
    return {str(_to_str(k)): str(_to_str(v)) for k, v in d.items()}


def _json_default(o: Any):
    if isinstance(o, BaseModel):
        return o.model_dump(mode="json")
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, (set, tuple)):
        return list(o)
    try:
        return str(o)
    except Exception:
        return repr(o)

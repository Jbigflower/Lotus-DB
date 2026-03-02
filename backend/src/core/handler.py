# 顶部：统一引入 Request、router_handler、依赖与服务
from fastapi import Request
from typing import Callable, Any, Union, Optional
import functools
import time
import inspect

# 顶部导入处
from config.logging import (
    get_trace_id,
    get_router_logger,
    get_service_logger,
    get_logic_logger,
    get_repo_logger,
    get_worker_logger,
)

from src.core.exceptions import (
    AppBaseException,
    map_exception_to_app,
    raise_with_context,
)


def router_handler(action: str):
    """
    通用路由层处理装饰器：
    - 自动记录 trace_id、user_id、action
    - 捕获异常并统一记录日志
    - 屏蔽敏感参数
    """

    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                logger = get_router_logger(func.__name__)
                trace_id = get_trace_id()
                start_time = time.time()

                # 提取 Request 和 user
                request: Request = next(
                    (a for a in args if isinstance(a, Request)), kwargs.get("request")
                )
                current_user = kwargs.get("current_user", None)
                user_name = current_user.username if current_user else "anonymous"

                logger.info(
                    f"[Router] [用户：{user_name} 执行：{action}] 请求开始",
                    extra={
                        "trace_id": trace_id,
                        "user_name": user_name,
                        "action": action,
                        "path": request.url.path if request else None,
                        "method": request.method if request else None,
                    },
                )

                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    logger.info(
                        f"[Router] [用户：{user_name} 执行：{action}] 请求成功 | 耗时 {elapsed:.3f}s",
                        extra={
                            "trace_id": trace_id,
                            "user_name": user_name,
                            "action": action,
                            "execution_time": elapsed,
                            "status": "success",
                        },
                    )
                    return result

                except Exception as e:
                    elapsed = time.time() - start_time
                    # 降噪：Router 层不打印堆栈，由 Repo 层或全局处理器打印
                    logger.warning(
                        f"[Router] [用户：{user_name} 执行：{action}] 请求失败 | 耗时 {elapsed:.3f}s",
                        extra={
                            "trace_id": trace_id,
                            "user_name": user_name,
                            "action": action,
                            "execution_time": elapsed,
                            "error_type": type(e).__name__,
                            "status": "error",
                        },
                        exc_info=False,
                    )
                    raise

            return async_wrapper

        else:
            raise TypeError("router_handler 仅支持 async def 路由函数")

    return decorator


def service_handler(action: str):
    """
    Service 层日志装饰器
    自动记录 trace_id、user_id、异常映射与日志输出
    与 performance_monitor 协同使用
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            self = args[0]
            logger = getattr(self, "logger", get_service_logger(func.__name__))
            trace_id = get_trace_id()
            user = kwargs.get("current_user", None)
            user_id = getattr(user, "id", None)

            start_time = time.time()

            # ---- 请求开始 ----
            logger.info(
                f"[Service] [用户：{user.username if user else 'anonymous'} 执行：{action}]",
                extra={
                    "trace_id": trace_id,
                    "action": action,
                    "user_id": user_id,
                },
            )

            try:
                result = await func(*args, **kwargs)

                # ---- 请求成功 ----
                duration = time.time() - start_time
                logger.info(
                    f"[Service] [用户：{user.username if user else 'anonymous'} 执行：{action}] 成功，耗时 {duration:.3f}s",
                    extra={
                        "trace_id": trace_id,
                        "action": action,
                        "user_id": user_id,
                        "execution_time": duration,
                        "status": "success",
                    },
                )

                return result

            except AppBaseException:
                # 已知业务异常不映射
                logger.debug(
                    f"[Service] [用户：{user.username if user else 'anonymous'} 执行：{action}] 参数为: {args} * {kwargs}",
                )
                raise

            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"[Service] [用户：{user.username if user else 'anonymous'} 执行：{action}] 参数为: {args} * {kwargs} 失败，错误原因：{str(e)}",
                    extra={
                        "trace_id": trace_id,
                        "action": action,
                        "user_id": user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "execution_time": duration,
                        "status": "error",
                    },
                    exc_info=True,
                )
                mapped_exc = map_exception_to_app(
                    e,
                    layer="Service",
                    context={
                        "trace_id": trace_id,
                        "user_id": user_id,
                        "action": action,
                    },
                )
                raise mapped_exc

        return async_wrapper

    return decorator


def logic_handler(action: str):
    """
    通用逻辑层装饰器：
    - 自动生成 trace_id
    - 自动记录逻辑层操作日志
    - 捕获异常并写入上下文日志
    - 兼容 performance_monitor
    """

    def decorator(func):
        if not inspect.iscoroutinefunction(func):
            raise TypeError("logic_handler 仅支持 async 函数")

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_logic_logger(func.__qualname__)
            trace_id = get_trace_id()
            start_time = time.time()

            logger.info(
                f"[Logic] [执行：{action}]",
                extra={"trace_id": trace_id, "action": action},
            )

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time

                logger.info(
                    f"[Logic] [执行：{action}] 成功 | 耗时 {elapsed:.3f}s",
                    extra={
                        "trace_id": trace_id,
                        "action": action,
                        "execution_time": elapsed,
                        "status": "success",
                    },
                )
                return result

            except AppBaseException:
                # 已知业务异常不映射
                logger.debug(
                    f"[Logic] [执行：{action}] 参数为: {args} * {kwargs}",
                )
                raise

            except Exception as e:
                elapsed = time.time() - start_time
                logger.warning(
                    f"[Logic] [执行：{action}] 参数为: {args} * {kwargs} 失败 | 耗时 {elapsed:.3f}s | 错误: {e}",
                    extra={
                        "trace_id": trace_id,
                        "action": action,
                        "error_type": type(e).__name__,
                        "execution_time": elapsed,
                    },
                    exc_info=True,
                )
                raise_with_context(
                    e, layer="Logic", context={"action": action, "trace_id": trace_id}
                )

        return wrapper

    return decorator


def repo_handler(action: str):
    """
    通用 Repo 层装饰器：
    - 自动生成 trace_id
    - 自动记录操作日志（含入参、出参摘要）
    - 自动捕获异常并写日志
    - 与 performance_monitor 兼容
    """

    def decorator(func):
        if not inspect.iscoroutinefunction(func):
            raise TypeError("repo_handler 仅支持 async 函数")

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            logger = get_repo_logger(func.__qualname__)
            trace_id = get_trace_id()
            start_time = time.time()

            # 输入参数日志（简化版，避免打印大对象）
            safe_kwargs = {
                k: (v if isinstance(v, (str, int, float, bool)) else str(type(v)))
                for k, v in kwargs.items()
            }

            logger.debug(
                f"[Repo] [执行：{action}] 开始",
                extra={
                    "trace_id": trace_id,
                    "action": action,
                    "params": safe_kwargs,
                },
            )

            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time

                logger.debug(
                    f"[Repo] [执行：{action}] 成功 | 耗时 {round(elapsed, 3)}s | 结果: {result}",
                    extra={
                        "trace_id": trace_id,
                        "action": action,
                        "execution_time": round(elapsed, 3),
                        "result": result,
                    },
                )
                return result

            # except AppBaseException:
            #     # 已知业务异常不映射
            #     logger.debug(
            #         f"[Repo] [执行：{action}] 参数为: {args} * {kwargs}",
            #     )
            #     raise

            except Exception as e:
                elapsed = time.time() - start_time

                logger.error(
                    f"[Repo] [执行：{action}] 参数为: {args} * {kwargs} 失败 | 耗时 {round(elapsed, 3)}s | 错误: {e}",
                    extra={
                        "trace_id": trace_id,
                        "action": action,
                        "execution_time": round(elapsed, 3),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                raise_with_context(
                    e, layer="Repo", context={"action": action, "trace_id": trace_id}
                )

        return wrapper

    return decorator


def task_handler(action: str):
    """
    异步后台任务装饰器：
    - 记录任务开始/成功/失败与耗时
    - 继承 Worker 设置的 trace_id
    - 兼容 async/sync 函数
    """

    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                logger = get_worker_logger(func.__name__)
                trace_id = get_trace_id()
                start_time = time.time()
                logger.info(
                    f"[Task] 开始执行 | {action}",
                    extra={"trace_id": trace_id, "action": action},
                )
                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    logger.info(
                        f"[Task] 执行成功 | {action} | 耗时 {elapsed:.3f}s",
                        extra={
                            "trace_id": trace_id,
                            "action": action,
                            "execution_time": elapsed,
                            "status": "success",
                        },
                    )
                    return result
                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"[Task] 执行失败 | {action} | 耗时 {elapsed:.3f}s | 错误: {e}",
                        extra={
                            "trace_id": trace_id,
                            "action": action,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "execution_time": elapsed,
                            "status": "error",
                        },
                        exc_info=True,
                    )
                    raise

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                logger = get_worker_logger(func.__name__)
                trace_id = get_trace_id()
                start_time = time.time()
                logger.info(
                    f"[Task] 开始执行 | {action}",
                    extra={"trace_id": trace_id, "action": action},
                )
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    logger.info(
                        f"[Task] 执行成功 | {action} | 耗时 {elapsed:.3f}s",
                        extra={
                            "trace_id": trace_id,
                            "action": action,
                            "execution_time": elapsed,
                            "status": "success",
                        },
                    )
                    return result
                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(
                        f"[Task] 执行失败 | {action} | 耗时 {elapsed:.3f}s | 错误: {e}",
                        extra={
                            "trace_id": trace_id,
                            "action": action,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "execution_time": elapsed,
                            "status": "error",
                        },
                        exc_info=True,
                    )
                    raise

            return sync_wrapper

    return decorator

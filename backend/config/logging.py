"""
全局日志配置模块

基于分层日志设计理念，为不同层级提供专门的日志记录器：
- Router 层：请求入口与响应出口的全链路记录
- Service 层：任务调度、异步执行、全局异常封装
- Logic 层：核心业务流程与分支行为
- Repo 层：数据库/缓存/文件IO 操作的追踪

支持 trace_id 穿透机制，实现请求链路追踪
"""

import logging
import logging.config
import os
import sys
import uuid
from contextvars import ContextVar
from typing import Optional, Dict, Any
from pathlib import Path
import traceback


# 全局 trace_id 上下文变量
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def set_trace_id(trace_id: Optional[str] = None) -> str:
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:6]

    trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> Optional[str]:
    if trace_id_var.get() is None:
        return None
    full_trace_id = str(trace_id_var.get())
    short_trace_id = f"{full_trace_id[:4]}***{full_trace_id[-4:]}"
    return short_trace_id


def clear_trace_id() -> None:
    trace_id_var.set(None)


class TraceIdFilter(logging.Filter):
    """为日志记录添加 trace_id"""

    def filter(self, record):
        trace_id = get_trace_id()
        record.trace_id = trace_id if trace_id else "no-trace"
        return True


class SensitiveDataFilter(logging.Filter):
    """过滤敏感数据"""

    SENSITIVE_KEYS = {"password", "token", "secret", "key", "auth", "credential"}

    def filter(self, record):
        # if hasattr(record, "msg") and isinstance(record.msg, str):
        #     # 简单的敏感数据过滤
        #     for key in self.SENSITIVE_KEYS:
        #         if key in record.msg.lower():
        #             record.msg = record.msg.replace(key, "***")
        return True


class FilteredStackFormatter(logging.Filter):
    """过滤异常堆栈中的 handler.py 行"""

    def filter(self, record):
        exc_info = getattr(record, "exc_info", None)
        if not exc_info or exc_info is False:
            return True
        if isinstance(exc_info, tuple):
            etype, evalue, tb = exc_info
            try:
                stack = traceback.format_exception(etype, evalue, tb)
                filtered_stack = [line for line in stack if "handler.py" not in line]
                record.exc_text = "".join(filtered_stack)
            except Exception:
                record.exc_text = None
        return True


def get_log_config() -> Dict[str, Any]:
    """获取日志配置字典"""

    # 确保日志目录存在
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "[%(asctime)s] [%(levelname)s] [trace:%(trace_id)s] %(message)s",
                "datefmt": "%m-%d %H:%M:%S",
            },
            "simple": {"format": "[%(levelname)s] [%(name)s] %(message)s"},
            "performance": {
                "format": "[%(asctime)s] [PERF] [%(name)s] [trace:%(trace_id)s] %(message)s",
                "datefmt": "%m-%d %H:%M:%S",
            },
        },
        "filters": {
            # trace-id 注入
            "trace_id_filter": {
                "()": TraceIdFilter,
            },
            # 脱敏
            "sensitive_filter": {
                "()": SensitiveDataFilter,
            },
            # 过滤 handler.py 堆栈
            "filtered_stack": {
                "()": FilteredStackFormatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "detailed",
                "filters": ["trace_id_filter", "sensitive_filter", "filtered_stack"],
                "stream": sys.stdout,
            },
            "file_all": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filters": ["trace_id_filter", "sensitive_filter"],
                "filename": "logs/app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8",
            },
            "file_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "detailed",
                "filters": ["trace_id_filter", "sensitive_filter"],
                "filename": "logs/error.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8",
            },
            # "file_performance": {
            #     "class": "logging.handlers.RotatingFileHandler",
            #     "level": "DEBUG",
            #     "formatter": "performance",
            #     "filters": ["trace_id_filter"],
            #     "filename": "logs/performance.log",
            #     "maxBytes": 10485760,  # 10MB
            #     "backupCount": 3,
            #     "encoding": "utf8",
            # },
            "file_worker_all": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filters": ["trace_id_filter", "sensitive_filter"],
                "filename": "logs/worker.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf8",
            },
            "file_worker_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "detailed",
                "filters": ["trace_id_filter", "sensitive_filter"],
                "filename": "logs/worker_error.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf8",
            },
        },
        "loggers": {
            # Router 层日志记录器
            "lotus.router": {
                "level": "INFO",
                "handlers": ["console", "file_all"],
                "propagate": False,
            },
            # Service 层日志记录器
            "lotus.service": {
                "level": "INFO",
                "handlers": ["console", "file_all", "file_error"],
                "propagate": False,
            },
            # Logic 层日志记录器
            "lotus.logic": {
                "level": "INFO",
                "handlers": ["console", "file_all", "file_error"],
                "propagate": False,
            },
            # Repo 层日志记录器
            "lotus.repo": {
                "level": "DEBUG",
                "handlers": ["console", "file_all", "file_error"],
                "propagate": False,
            },
            # 性能监控日志记录器
            # "lotus.performance": {
            #     "level": "DEBUG",
            #     "handlers": ["file_performance"],
            #     "propagate": False,
            # },
            # # Celery 任务日志记录器
            # "lotus.celery": {
            #     "level": "INFO",
            #     "handlers": ["console", "file_all"],
            #     "propagate": False,
            # },
            "lotus.worker": {
                "level": "INFO",
                "handlers": ["console", "file_worker_all", "file_worker_error"],
                "propagate": False,
            },
            "lotus.beat": {
                "level": "INFO",
                "handlers": ["console", "file_worker_all", "file_worker_error"],
                "propagate": False,
            },
            # 第三方库日志控制
            "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
            "fastapi": {"level": "INFO", "handlers": ["console"], "propagate": False},
        },
        "root": {"level": "INFO", "handlers": ["console", "file_all"]},
    }


def setup_logging(log_level: "INFO") -> None:
    """
    初始化日志配置

    Args:
        log_level: 日志级别，默认为 INFO
    """
    config = get_log_config()

    # 根据环境变量调整日志级别
    env_log_level = os.getenv("LOG_LEVEL", log_level).upper()

    # 更新所有处理器的日志级别
    for handler_config in config["handlers"].values():
        if handler_config.get("level") == "INFO":
            handler_config["level"] = env_log_level

    # 应用配置
    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的日志记录器

    Args:
        name: 日志记录器名称，建议使用分层命名：
              - lotus.router.{module_name}
              - lotus.service.{module_name}
              - lotus.logic.{module_name}
              - lotus.repo.{module_name}

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    return logging.getLogger(name)


# 初始化日志配置（模块导入时自动执行）
setup_logging(log_level="DEBUG")


# 便捷的日志记录器获取函数
def get_router_logger(module_name: str) -> logging.Logger:
    """获取 Router 层日志记录器"""
    return get_logger(f"lotus.router.{module_name}")


def get_service_logger(module_name: str) -> logging.Logger:
    """获取 Service 层日志记录器"""
    return get_logger(f"lotus.service.{module_name}")


def get_logic_logger(module_name: str) -> logging.Logger:
    """获取 Logic 层日志记录器"""
    return get_logger(f"lotus.logic.{module_name}")


def get_repo_logger(module_name: str) -> logging.Logger:
    """获取 Repo 层日志记录器"""
    return get_logger(f"lotus.repo.{module_name}")


def get_performance_logger() -> logging.Logger:
    """获取性能监控日志记录器"""
    return get_logger("lotus.performance")


def get_celery_logger() -> logging.Logger:
    """获取 Celery 任务日志记录器"""
    return get_logger("lotus.celery")


def get_worker_logger(module_name: str) -> logging.Logger:
    """获取异步后台 Worker 日志记录器"""
    return get_logger(f"lotus.worker.{module_name}")


def get_beat_logger(module_name: str) -> logging.Logger:
    """获取定时调度器 Beat 日志记录器"""
    return get_logger(f"lotus.beat.{module_name}")

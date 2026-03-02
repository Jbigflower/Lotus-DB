from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AppBaseException(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str,
        layer: str,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.layer = layer
        self.details = details or {}
        self.context = context or {}
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "type": self.__class__.__name__,
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
                "layer": self.layer,
            }
        }


# ===== 分层异常基类 =====
class DBError(AppBaseException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "DB_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class RepoError(AppBaseException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "REPO_ERROR",
        layer: str = "Repo",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class LogicError(AppBaseException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "LOGIC_ERROR",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class ServiceError(AppBaseException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "SERVICE_ERROR",
        layer: str = "Service",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class RouterError(AppBaseException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "ROUTER_ERROR",
        layer: str = "Router",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


# ===== DB 层专用异常类型 =====
class DBConnectionError(DBError):
    """数据库连接异常"""

    def __init__(
        self,
        message: str = "数据库连接失败",
        *,
        status_code: int = 503,
        error_code: str = "DB_CONNECTION_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DBTimeoutError(DBError):
    """数据库操作超时异常"""

    def __init__(
        self,
        message: str = "数据库操作超时",
        *,
        status_code: int = 504,
        error_code: str = "DB_TIMEOUT_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DBConfigurationError(DBError):
    """数据库配置异常"""

    def __init__(
        self,
        message: str = "数据库配置错误",
        *,
        status_code: int = 500,
        error_code: str = "DB_CONFIG_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DBInitializationError(DBError):
    """数据库初始化异常"""

    def __init__(
        self,
        message: str = "数据库初始化失败",
        *,
        status_code: int = 500,
        error_code: str = "DB_INIT_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DBOperationError(DBError):
    """数据库操作异常"""

    def __init__(
        self,
        message: str = "数据库操作失败",
        *,
        status_code: int = 500,
        error_code: str = "DB_OPERATION_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DBTransactionError(DBError):
    """数据库事务异常"""

    def __init__(
        self,
        message: str = "数据库事务失败",
        *,
        status_code: int = 500,
        error_code: str = "DB_TRANSACTION_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DBIndexError(DBError):
    """数据库索引异常"""

    def __init__(
        self,
        message: str = "数据库索引操作失败",
        *,
        status_code: int = 500,
        error_code: str = "DB_INDEX_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


# MongoDB 专用异常
class MongoDBError(DBError):
    """MongoDB 专用异常基类"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "MONGODB_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


# Redis 专用异常
class RedisError(DBError):
    """Redis 专用异常基类"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "REDIS_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


# 向量数据库专用异常
class VectorDBError(DBError):
    """向量数据库专用异常基类"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "VECTOR_DB_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class ChromaDBError(VectorDBError):
    """ChromaDB 专用异常"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "CHROMA_DB_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class LanceDBError(VectorDBError):
    """LanceDB 专用异常"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "LANCE_DB_ERROR",
        layer: str = "DB",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


# ===== Repo 层标准异常（供 base_repo 及各仓储模块直接引用）=====
class BaseRepoException(RepoError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "REPO_ERROR",
        layer: str = "Repo",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DocumentNotFoundError(BaseRepoException):
    def __init__(
        self,
        message: str = "文档未找到",
        *,
        status_code: int = 404,
        error_code: str = "NOT_FOUND",
        layer: str = "Repo",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class DuplicateDocumentError(BaseRepoException):
    def __init__(
        self,
        message: str = "文档重复",
        *,
        status_code: int = 409,
        error_code: str = "CONFLICT",
        layer: str = "Repo",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class RepoValidationError(BaseRepoException):
    def __init__(
        self,
        message: str = "数据验证失败",
        *,
        status_code: int = 400,
        error_code: str = "VALIDATION_ERROR",
        layer: str = "Repo",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


# ===== 业务异常（Logic 层常见类型）=====
class ValidationError(LogicError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "VALIDATION_ERROR",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class NotFoundError(LogicError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 404,
        error_code: str = "NOT_FOUND",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class ConflictError(LogicError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 409,
        error_code: str = "CONFLICT",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class UnauthorizedError(LogicError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 401,
        error_code: str = "UNAUTHORIZED",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class ForbiddenError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 403,
        error_code: str = "FORBIDDEN",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class BadRequestError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "BAD_REQUEST",
        layer: str = "Logic",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class InternalServerError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "INTERNAL_SERVER_ERROR",
        layer: str = "Service",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


class NotImplementedServiceError(ServiceError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 501,
        error_code: str = "NOT_IMPLEMENTED",
        layer: str = "Service",
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            status_code=status_code,
            error_code=error_code,
            layer=layer,
            details=details,
            context=context,
            cause=cause,
        )


def map_exception_to_app(
    exc: Exception, *, layer: str, context: Optional[Dict[str, Any]] = None
) -> AppBaseException:
    """
    异常类型的映射与包装工厂：
        自动识别各层异常 和 python 内部异常 + 数据库常用异常 并转换为统一的 AppBaseException。
    - 保留原始异常信息（message/cause）
    - 基于异常类型映射为标准化错误码/HTTP 状态码
    """
    # 统一处理已是 AppBaseException 的异常
    if isinstance(exc, AppBaseException):
        return exc

    # Repo 层标准异常映射
    if isinstance(exc, BaseRepoException):
        if isinstance(exc, DocumentNotFoundError):
            return NotFoundError(str(exc), layer="Repo", context=context, cause=exc)
        if isinstance(exc, RepoValidationError):
            return ValidationError(str(exc), layer="Repo", context=context, cause=exc)
        if isinstance(exc, DuplicateDocumentError):
            return ConflictError(str(exc), layer="Repo", context=context, cause=exc)
        return RepoError(str(exc), layer="Repo", context=context, cause=exc)

    # DB 层异常映射 - MongoDB
    if "pymongo" in str(type(exc).__module__) or "motor" in str(type(exc).__module__):
        from pymongo.errors import (
            ConnectionFailure,
            ServerSelectionTimeoutError,
            DuplicateKeyError,
            OperationFailure,
            ConfigurationError,
        )

        if isinstance(exc, (ConnectionFailure, ServerSelectionTimeoutError)):
            return DBConnectionError(str(exc), layer=layer, context=context, cause=exc)
        if isinstance(exc, DuplicateKeyError):
            return ConflictError(str(exc), layer=layer, context=context, cause=exc)
        if isinstance(exc, ConfigurationError):
            return DBConfigurationError(
                str(exc), layer=layer, context=context, cause=exc
            )
        if isinstance(exc, OperationFailure):
            return DBOperationError(str(exc), layer=layer, context=context, cause=exc)
        return MongoDBError(str(exc), layer=layer, context=context, cause=exc)

    # DB 层异常映射 - Redis
    if "redis" in str(type(exc).__module__):
        try:
            from redis.exceptions import (
                ConnectionError as RedisConnectionError,
                TimeoutError as RedisTimeoutError,
            )

            if isinstance(exc, RedisConnectionError):
                return DBConnectionError(
                    str(exc), layer=layer, context=context, cause=exc
                )
            if isinstance(exc, RedisTimeoutError):
                return DBTimeoutError(str(exc), layer=layer, context=context, cause=exc)
        except ImportError:
            pass
        return RedisError(str(exc), layer=layer, context=context, cause=exc)

    # DB 层异常映射 - ChromaDB
    if "chromadb" in str(type(exc).__module__):
        return ChromaDBError(str(exc), layer=layer, context=context, cause=exc)

    # DB 层异常映射 - LanceDB
    if "lancedb" in str(type(exc).__module__):
        return LanceDBError(str(exc), layer=layer, context=context, cause=exc)

    # 常见内置异常映射
    if isinstance(exc, PermissionError):
        return ForbiddenError(str(exc), layer=layer, context=context, cause=exc)
    if isinstance(exc, FileNotFoundError):
        return NotFoundError(str(exc), layer=layer, context=context, cause=exc)
    if isinstance(exc, ValueError):
        # 更偏向业务验证错误
        return ValidationError(str(exc), layer=layer, context=context, cause=exc)
    if isinstance(exc, NotImplementedError):
        return NotImplementedServiceError(
            str(exc), layer=layer, context=context, cause=exc
        )
    if isinstance(exc, TimeoutError):
        return DBTimeoutError(str(exc), layer=layer, context=context, cause=exc)
    if isinstance(exc, ConnectionError):
        return DBConnectionError(str(exc), layer=layer, context=context, cause=exc)

    # 默认兜底：内部错误
    return InternalServerError(
        "服务器内部错误",
        layer=layer,
        details={"reason": str(exc)},
        context=context,
        cause=exc,
    )


def raise_with_context(
    exc: Exception, *, layer: str, context: Optional[Dict[str, Any]] = None
):
    app_exc = map_exception_to_app(exc, layer=layer, context=context)
    raise app_exc from exc


# FASTAPI 异常注册（全局处理器）
def register_exception_handlers(app: FastAPI):
    @app.exception_handler(AppBaseException)
    async def app_exception_handler(request: Request, exc: AppBaseException):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        app_exc = map_exception_to_app(
            exc, layer="Core", context={"path": str(request.url)}
        )

        return JSONResponse(
            status_code=app_exc.status_code,
            content=app_exc.to_dict(),
        )

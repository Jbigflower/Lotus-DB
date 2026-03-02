import uuid
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from config.logging import set_trace_id, get_router_logger
# from src.core.api.base import RequestLoggingMiddleware

logger = get_router_logger("middleware")


class TraceIdMiddleware(BaseHTTPMiddleware):
    """
    Trace ID 中间件
    为每个请求生成唯一的 trace_id，用于日志追踪
    """

    async def dispatch(self, request: Request, call_next):
        # 生成或获取 trace_id
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())

        # 设置到上下文中
        set_trace_id(trace_id)

        # 记录请求开始
        logger.info(
            f"请求开始 - {request.method} {request.url.path}",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        try:
            # 处理请求
            response = await call_next(request)

            # 在响应头中添加 trace_id
            response.headers["X-Trace-ID"] = trace_id

            # 记录请求完成
            logger.info(
                f"请求完成 - {request.method} {request.url.path} - {response.status_code}",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                },
            )

            return response

        except Exception as e:
            # 记录请求异常
            logger.error(
                f"请求异常 - {request.method} {request.url.path}",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise


def register_middlewares(app):
    # 添加 Trace ID 中间件（需要在其他中间件之前）
    app.add_middleware(TraceIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://localhost:15174",
            "http://127.0.0.1:15174",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # app.add_middleware(RequestLoggingMiddleware)

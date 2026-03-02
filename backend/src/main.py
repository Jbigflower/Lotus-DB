import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

from config.logging import get_logger
from src.core.database import init_databases, close_databases
from src.core.exceptions import register_exception_handlers
from src.core.middleware import register_middlewares
from src.core.routers import register_routers
from src.core.docs import custom_openapi, custom_swagger_ui
from src.plugins.manager import plugin_manager
from src.logic.users.auth_logic import AuthLogic
from src.services.sync.manager import sync_manager


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动Lotus-DB后端...")
    os.makedirs("logs", exist_ok=True)

    # 加载插件并注入到 app.state
    plugin_manager.scan_and_load()
    app.state.plugin_manager = plugin_manager
    logger.info("插件加载成功...")

    await init_databases()

    # 初始化默认管理员
    await AuthLogic().init_admin_account()

    # 启动同步服务
    await sync_manager.start_all()

    yield
    logger.info("关闭Lotus-DB后端...")
    
    # 停止同步服务
    await sync_manager.stop_all()
    
    await close_databases()


app = FastAPI(
    title="Lotus-DB后端API",
    version="1.0.0",
    description="Lotus-DB后端服务",
    lifespan=lifespan,
    docs_url=None,  # 用自定义UI
)

# 注册中间件、异常、路由、OpenAPI
register_middlewares(app)
register_exception_handlers(app)
register_routers(app)
app.openapi = lambda: custom_openapi(app)


@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    return custom_swagger_ui(app)


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "欢迎使用Lotus-DB后端API",
        "version": "1.0.0",
        "status": "healthy",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

#!/usr/bin/env python3
"""
应用启动脚本
"""

import sys
import uvicorn
from config.setting import settings
from config.logging import get_logger, setup_logging

# 输出当前日志等级
logger = get_logger(__name__)

# 启动应用
if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else settings.app.host
    port = int(sys.argv[2]) if len(sys.argv) > 2 else settings.app.port
    reload = settings.app.debug
    print(f"\n🚀 启动应用: http://{host}:{port}")
    print(f"🔍 API文档: http://{host}:{port}/docs")
    print(f"📝 ReDoc文档: http://{host}:{port}/redoc\n")

    # 启动uvicorn服务器
    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=["src"],   # FIX Huge Info：[INFO] [trace:no-trace] 1 change detected
        workers=1 if reload else None,
    )

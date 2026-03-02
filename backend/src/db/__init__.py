"""
数据库层模块

提供 MongoDB、Redis、Chroma 等数据库的连接管理
仅负责数据库连接和客户端管理，不包含任何CRUD操作或业务逻辑
"""

from .mongo_db import (
    MongoManager,
    init_mongo,
    close_mongo,
    get_mongo_manager,
    get_mongo_client,
    get_mongo_db,
    get_movies_collection,
    get_assets_collection,
    get_users_collection,
    get_user_assets_collection,
    get_watch_history_collection,
    get_tasks_collection,
    get_logs_collection,
    get_libraries_collection,
)

from .redis_db import (
    RedisManager,
    init_redis,
    close_redis,
    get_redis_manager,
    get_redis_client,
)

from .chroma_db import (
    ChromaManager,
    init_chroma,
    close_chroma,
    get_chroma_manager,
    get_chroma_client,
)

from .lance_db import (
    LanceDBManager,
    init_lance,
    close_lance,
    get_lance_manager,
    get_lance_db,
)

__all__ = [
    # MongoDB
    "MongoManager",
    "init_mongo",
    "close_mongo",
    "get_mongo_manager",
    "get_mongo_client",
    "get_mongo_db",
    "get_movies_collection",
    "get_assets_collection",
    "get_users_collection",
    "get_user_assets_collection",
    "get_watch_history_collection",
    "get_tasks_collection",
    "get_logs_collection",
    "get_libraries_collection",
    # Redis
    "RedisManager",
    "init_redis",
    "close_redis",
    "get_redis_manager",
    "get_redis_client",
    # Chroma
    "ChromaManager",
    "init_chroma",
    "close_chroma",
    "get_chroma_manager",
    "get_chroma_client",
    # LanceDB
    "LanceDBManager",
    "init_lance",
    "close_lance",
    "get_lance_manager",
    "get_lance_db",
]

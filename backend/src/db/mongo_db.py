"""
MongoDB 连接管理器

提供 MongoDB 客户端的单例管理、连接池、事务支持和索引管理
支持异步操作和连接生命周期管理
"""

import asyncio
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
)
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo import IndexModel, ASCENDING, DESCENDING, TEXT

from config.setting import get_settings
from config.logging import get_logger
from src.core.exceptions import (
    DBConnectionError,
    DBTimeoutError,
    DBConfigurationError,
    DBInitializationError,
    DBOperationError,
    DBIndexError,
    raise_with_context,
)

logger = get_logger(__name__)


class MongoManager:
    """MongoDB 连接管理器"""

    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._settings = get_settings().database
        self._is_connected = False

    async def connect(self) -> None:
        """建立 MongoDB 连接"""
        if self._is_connected:
            logger.warning("MongoDB 已经连接，跳过重复连接")
            return

        try:
            logger.info(
                f"正在连接 MongoDB: {self._settings.mongo_host}:{self._settings.mongo_port}"
            )

            # 创建客户端
            self._client = AsyncIOMotorClient(
                self._settings.mongo_url,
                serverSelectionTimeoutMS=5000,  # 5秒超时
                connectTimeoutMS=10000,  # 10秒连接超时
                maxPoolSize=50,  # 最大连接池大小
                minPoolSize=5,  # 最小连接池大小
                maxIdleTimeMS=30000,  # 30秒空闲超时
                uuidRepresentation='standard',  # 设置 UUID 表示形式
            )

            # 测试连接
            await self._client.admin.command("ping")

            # 获取数据库
            self._db = self._client[self._settings.mongo_db]

            self._is_connected = True
            logger.info("MongoDB 连接成功")

            # 创建索引
            await self._create_indexes()

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB 连接失败: {e}")
            raise_with_context(
                e,
                layer="DB",
                context={
                    "host": self._settings.mongo_host,
                    "port": self._settings.mongo_port,
                },
            )
        except Exception as e:
            logger.error(f"MongoDB 连接时发生未知错误: {e}")
            raise_with_context(e, layer="DB", context={"operation": "connect"})

    async def disconnect(self) -> None:
        """断开 MongoDB 连接"""
        if self._client is not None:
            logger.info("正在断开 MongoDB 连接")
            self._client.close()
            self._client = None
            self._db = None
            self._is_connected = False
            logger.info("MongoDB 连接已断开")

    async def _create_indexes(self) -> None:
        """创建数据库索引"""
        if self._db is None:
            return

        logger.info("开始创建 MongoDB 索引")

        try:
            # movies 集合索引
            movies_indexes = [
                IndexModel(
                    [
                        ("title", TEXT),
                        ("title_cn", TEXT),
                        ("description", TEXT),
                        ("description_cn", TEXT),
                    ]
                ),
                IndexModel([("release_date", DESCENDING)]),
                IndexModel([("genres", ASCENDING)]),
                IndexModel([("rating", DESCENDING)]),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("is_deleted", ASCENDING)]),
                # 唯一性索引：library_id + title + release_date
                IndexModel(
                    [("library_id", ASCENDING), ("title", ASCENDING), ("release_date", ASCENDING)], unique=True
                ),
            ]
            await self._db.movies.create_indexes(movies_indexes)

            # assets 集合索引
            assets_indexes = [
                IndexModel([("movie_id", ASCENDING), ("type", ASCENDING)]),
                IndexModel([("library_id", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("is_deleted", ASCENDING)]),
            ]
            await self._db.assets.create_indexes(assets_indexes)

            # users 集合索引
            users_indexes = [
                IndexModel([("username", ASCENDING)], unique=True),
                IndexModel([("email", ASCENDING)], unique=True),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("is_deleted", ASCENDING)]),
            ]
            await self._db.users.create_indexes(users_indexes)

            # user_assets 集合索引
            user_assets_indexes = [
                IndexModel([("user_id", ASCENDING), ("movie_id", ASCENDING)]),
                IndexModel([("user_id", ASCENDING), ("type", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("is_deleted", ASCENDING)]),
            ]
            await self._db.user_assets.create_indexes(user_assets_indexes)

            # watch_histories 集合索引
            watch_histories_indexes = [
                IndexModel(
                    [("user_id", ASCENDING), ("asset_id", ASCENDING), ("type", ASCENDING)], unique=True
                ),
                IndexModel([("user_id", ASCENDING), ("last_watched", DESCENDING)]),
                IndexModel([("movie_id", ASCENDING)]),
                IndexModel([("asset_id", ASCENDING)]),
                IndexModel([("last_watched", DESCENDING)]),
            ]
            await self._db.watch_histories.create_indexes(watch_histories_indexes)

            # user_custom_lists 集合索引
            user_custom_lists_indexes = [
                # IndexModel([("user_id", ASCENDING), ("type", ASCENDING)], unique=True, partialFilterExpression={"type": {"$in": ["favorite", "watchlist"]}}),
                IndexModel([("user_id", ASCENDING), ("type", ASCENDING)]),
                IndexModel([("user_id", ASCENDING), ("name", ASCENDING)], unique=True),
                IndexModel([("created_at", DESCENDING)]),
            ]
            await self._db.user_custom_lists.create_indexes(user_custom_lists_indexes)

            # tasks 集合索引
            tasks_indexes = [
                IndexModel([("status", ASCENDING), ("created_at", DESCENDING)]),
                IndexModel([("task_type", ASCENDING)]),
                IndexModel([("movie_id", ASCENDING), ("asset_id", ASCENDING)]),
                IndexModel([("created_at", DESCENDING)]),
            ]
            await self._db.tasks.create_indexes(tasks_indexes)

            # libraries 集合索引
            libraries_indexes = [
                IndexModel([("user_id", ASCENDING), ("name", ASCENDING)], unique=True),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("is_deleted", ASCENDING)]),
            ]
            await self._db.libraries.create_indexes(libraries_indexes)

            logger.info("MongoDB 索引创建完成")

        except Exception as e:
            logger.error(f"创建 MongoDB 索引时发生错误: {e}")
            # 索引创建失败不应该阻止应用启动，但需要记录详细错误信息
            raise_with_context(
                DBIndexError(f"索引创建失败: {str(e)}"),
                layer="DB",
                context={"operation": "create_indexes"},
            )

    @property
    def client(self) -> AsyncIOMotorClient:
        """获取 MongoDB 客户端"""
        if self._client is None:
            raise DBInitializationError("MongoDB 客户端未初始化，请先调用 connect()")
        return self._client

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """获取 MongoDB 数据库"""
        if self._db is None:
            raise DBInitializationError("MongoDB 数据库未初始化，请先调用 connect()")
        return self._db

    def get_collection(self, name: str) -> AsyncIOMotorCollection:
        """获取指定名称的集合"""
        return self.db[name]

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected

    async def ping(self) -> bool:
        """测试连接是否正常"""
        try:
            if self._client is not None:
                await self._client.admin.command("ping")
                return True
        except Exception as e:
            logger.error(f"MongoDB ping 失败: {e}")
            # ping 失败不抛出异常，只返回 False
        return False

    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        if self._client is None:
            raise DBInitializationError("MongoDB 客户端未初始化")

        try:
            async with await self._client.start_session() as session:
                async with session.start_transaction():
                    try:
                        yield session
                    except Exception as e:
                        await session.abort_transaction()
                        raise_with_context(
                            e, layer="DB", context={"operation": "transaction"}
                        )
        except Exception as e:
            raise_with_context(
                e, layer="DB", context={"operation": "start_transaction"}
            )

    async def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        if self._db is None:
            return {}

        try:
            stats = await self._db.command("dbStats")
            return {
                "collections": stats.get("collections", 0),
                "objects": stats.get("objects", 0),
                "dataSize": stats.get("dataSize", 0),
                "storageSize": stats.get("storageSize", 0),
                "indexes": stats.get("indexes", 0),
                "indexSize": stats.get("indexSize", 0),
            }
        except Exception as e:
            logger.error(f"获取数据库统计信息失败: {e}")
            # 统计信息获取失败不抛出异常，返回空字典
            return {}


# 全局 MongoDB 管理器实例
_mongo_manager: Optional[MongoManager] = None


async def init_mongo() -> MongoManager:
    """初始化 MongoDB 连接"""
    global _mongo_manager

    if _mongo_manager is None:
        _mongo_manager = MongoManager()

    if not _mongo_manager.is_connected:
        await _mongo_manager.connect()

    return _mongo_manager


async def close_mongo() -> None:
    """关闭 MongoDB 连接"""
    global _mongo_manager

    if _mongo_manager:
        await _mongo_manager.disconnect()
        _mongo_manager = None


def get_mongo_manager() -> MongoManager:
    """获取 MongoDB 管理器实例"""
    global _mongo_manager
    if _mongo_manager is None:
        raise DBInitializationError("MongoDB 管理器未初始化，请先调用 init_mongo()")
    return _mongo_manager


def get_mongo_client() -> AsyncIOMotorClient:
    """获取 MongoDB 客户端"""
    return get_mongo_manager().client


def get_mongo_db() -> AsyncIOMotorDatabase:
    """获取 MongoDB 数据库"""
    return get_mongo_manager().db


def get_collection(name: str) -> AsyncIOMotorCollection:
    """获取指定名称的集合"""
    if not name:
        raise DBConfigurationError("集合名称不能为空")
    return get_mongo_db()[name]


# 便捷的集合访问函数
def get_movies_collection() -> AsyncIOMotorCollection:
    """获取 movies 集合"""
    return get_collection("movies")


def get_assets_collection() -> AsyncIOMotorCollection:
    """获取 assets 集合"""
    return get_collection("assets")


def get_users_collection() -> AsyncIOMotorCollection:
    """获取 users 集合"""
    return get_collection("users")


def get_user_assets_collection() -> AsyncIOMotorCollection:
    """获取 user_assets 集合"""
    return get_collection("user_assets")


def get_watch_history_collection() -> AsyncIOMotorCollection:
    """获取 watch_history 集合"""
    return get_collection("watch_history")


def get_tasks_collection() -> AsyncIOMotorCollection:
    """获取 tasks 集合"""
    return get_collection("tasks")


def get_logs_collection() -> AsyncIOMotorCollection:
    """获取 logs 集合"""
    return get_collection("logs")


def get_libraries_collection() -> AsyncIOMotorCollection:
    """获取 libraries 集合"""
    return get_collection("libraries")

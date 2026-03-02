"""
Redis 连接管理器

提供 Redis 客户端的连接管理
仅负责连接管理和底层连接封装，不包含任何数据操作
"""

from typing import Optional, Dict, Any

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from config.setting import get_settings
from config.logging import get_logger
from src.core.exceptions import (
    DBConnectionError,
    DBTimeoutError,
    DBConfigurationError,
    DBInitializationError,
    RedisError as CustomRedisError,
    raise_with_context,
)

logger = get_logger(__name__)


class RedisManager:
    """Redis 连接管理器

    职责：
    - 管理 Redis 客户端连接和连接池
    - 提供连接状态监控
    - 不包含任何数据操作或业务逻辑
    """

    def __init__(self):
        self._client: Optional[Redis] = None
        self._pool: Optional[ConnectionPool] = None
        self._settings = get_settings().database
        self._is_connected = False

    async def connect(self) -> None:
        """建立 Redis 连接"""
        if self._is_connected:
            logger.warning("Redis 已经连接，跳过重复连接")
            return

        try:
            logger.info(
                f"正在连接 Redis: {self._settings.redis_host}:{self._settings.redis_port}"
            )

            # 创建连接池
            self._pool = ConnectionPool(
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                db=self._settings.redis_db,
                password=self._settings.redis_password,
                max_connections=self._settings.redis_max_connections,
                retry_on_timeout=True,
                socket_connect_timeout=5,  # 5秒连接超时
                socket_timeout=5,  # 5秒读写超时
                decode_responses=True,  # 自动解码响应
                encoding="utf-8",
            )

            # 创建客户端
            self._client = Redis(connection_pool=self._pool)

            # 测试连接
            await self._client.ping()

            self._is_connected = True
            logger.info("Redis 连接成功")

        except ConnectionError as e:
            raise_with_context(
                DBConnectionError(
                    f"Redis 连接失败: {self._settings.redis_host}:{self._settings.redis_port}"
                ),
                original_exception=e,
                context={
                    "host": self._settings.redis_host,
                    "port": self._settings.redis_port,
                    "db": self._settings.redis_db,
                },
            )
        except TimeoutError as e:
            raise_with_context(
                DBTimeoutError(
                    f"Redis 连接超时: {self._settings.redis_host}:{self._settings.redis_port}"
                ),
                original_exception=e,
                context={
                    "host": self._settings.redis_host,
                    "port": self._settings.redis_port,
                    "timeout": 5,
                },
            )
        except RedisError as e:
            raise_with_context(
                CustomRedisError(f"Redis 错误: {str(e)}"),
                original_exception=e,
                context={
                    "host": self._settings.redis_host,
                    "port": self._settings.redis_port,
                },
            )
        except Exception as e:
            raise_with_context(
                DBConnectionError(f"Redis 连接失败: {str(e)}"),
                original_exception=e,
                context={
                    "host": self._settings.redis_host,
                    "port": self._settings.redis_port,
                },
            )

    async def disconnect(self) -> None:
        """断开 Redis 连接"""
        if self._client:
            logger.info("正在断开 Redis 连接")
            await self._client.close()
            self._client = None

        if self._pool:
            await self._pool.disconnect()
            self._pool = None

        self._is_connected = False
        logger.info("Redis 连接已断开")

    @property
    def client(self) -> Redis:
        """获取 Redis 客户端"""
        if self._client is None:
            raise DBInitializationError("Redis 客户端未初始化，请先调用 connect()")
        return self._client

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected

    async def ping(self) -> bool:
        """测试连接是否正常"""
        try:
            if self._client:
                await self._client.ping()
                return True
        except Exception as e:
            logger.error(f"Redis ping 失败: {e}")
        return False

    async def get_info(self) -> Dict[str, Any]:
        """获取 Redis 服务器信息"""
        try:
            info = await self.client.info()
            return {
                "version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            logger.error(f"获取 Redis 信息失败: {e}")
            return {}


# 全局 Redis 管理器实例
_redis_manager: Optional[RedisManager] = None


async def init_redis() -> RedisManager:
    """初始化 Redis 连接"""
    global _redis_manager

    if _redis_manager is None:
        _redis_manager = RedisManager()

    if not _redis_manager.is_connected:
        await _redis_manager.connect()

    return _redis_manager


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis_manager

    if _redis_manager:
        await _redis_manager.disconnect()
        _redis_manager = None


def get_redis_manager() -> RedisManager:
    """获取 Redis 管理器实例"""
    global _redis_manager
    if _redis_manager is None:
        raise DBInitializationError("Redis 管理器未初始化，请先调用 init_redis()")
    return _redis_manager


def get_redis_client() -> Redis:
    """获取 Redis 客户端"""
    return get_redis_manager().client

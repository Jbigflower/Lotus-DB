"""
ChromaDB 连接管理器

提供 ChromaDB 客户端的连接管理
仅负责连接管理和底层连接封装，不包含任何数据操作
"""

from typing import Optional, Dict, Any
from pathlib import Path

import chromadb
from chromadb import Client
from chromadb.config import Settings
from chromadb.api.models.Collection import Collection

from config.setting import get_settings
from config.logging import get_logger
from src.core.exceptions import (
    DBConnectionError,
    DBConfigurationError,
    DBInitializationError,
    VectorDBError,
    ChromaDBError,
    raise_with_context,
)

logger = get_logger(__name__)


class ChromaManager:
    """Chroma 向量数据库管理器

    职责：
    - 管理 Chroma 客户端连接
    - 提供客户端初始化和配置
    - 不包含任何数据操作或业务逻辑
    """

    def __init__(self):
        self._client: Optional[Client] = None
        self._db_settings = get_settings().database
        self._is_connected = False

    async def connect(self) -> None:
        """建立 Chroma 连接"""
        if self._is_connected:
            logger.warning("Chroma 已经连接，跳过重复连接")
            return

        try:
            logger.info(
                f"正在连接 Chroma: {self._db_settings.chroma_host}:{self._db_settings.chroma_port}"
            )

            # 根据配置选择连接方式
            if self._db_settings.chroma_persist_directory:
                # 持久化存储模式
                persist_path = Path(self._db_settings.chroma_persist_directory)
                persist_path.mkdir(parents=True, exist_ok=True)

                settings = Settings(
                    persist_directory=str(persist_path), anonymized_telemetry=False
                )
                self._client = chromadb.PersistentClient(settings=settings)
                logger.info(f"Chroma 持久化客户端已连接: {persist_path}")

            else:
                # HTTP 客户端模式
                settings = Settings(
                    chroma_server_host=self._db_settings.chroma_host,
                    chroma_server_http_port=self._db_settings.chroma_port,
                    anonymized_telemetry=False,
                )
                self._client = chromadb.HttpClient(
                    host=self._db_settings.chroma_host,
                    port=self._db_settings.chroma_port,
                    settings=settings,
                )
                logger.info(
                    f"Chroma HTTP 客户端已连接: {self._db_settings.chroma_host}:{self._db_settings.chroma_port}"
                )

            # 测试连接
            await self._test_connection()

            self._is_connected = True
            logger.info("Chroma 连接成功")

        except ValueError as e:
            if "path" in str(e).lower():
                raise_with_context(
                    DBConfigurationError(f"ChromaDB 路径配置错误: {str(e)}"),
                    original_exception=e,
                    context={
                        "persist_directory": self._db_settings.chroma_persist_directory
                    },
                )
            else:
                raise_with_context(
                    ChromaDBError(f"ChromaDB 配置错误: {str(e)}"),
                    original_exception=e,
                    context={
                        "persist_directory": self._db_settings.chroma_persist_directory
                    },
                )
        except Exception as e:
            raise_with_context(
                DBConnectionError(f"ChromaDB 连接失败: {str(e)}"),
                original_exception=e,
                context={
                    "host": self._db_settings.chroma_host,
                    "port": self._db_settings.chroma_port,
                },
            )

    async def disconnect(self) -> None:
        """断开 Chroma 连接"""
        if self._client:
            logger.info("正在断开 Chroma 连接")
            self._client = None

        self._is_connected = False
        logger.info("Chroma 连接已断开")

    async def _test_connection(self) -> None:
        """测试连接是否正常"""
        try:
            # 尝试获取版本信息
            version = self._client.get_version()
            logger.info(f"Chroma 版本: {version}")
        except Exception as e:
            logger.error(f"Chroma 连接测试失败: {e}")
            raise

    @property
    def client(self) -> Client:
        """获取 Chroma 客户端"""
        if not self._client:
            raise DBInitializationError("Chroma 客户端未初始化，请先调用 connect()")
        return self._client

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected

    def get_or_create_collection(self, name: str) -> Collection:
        """
        获取已有 Collection，如果不存在则创建
        返回 Collection 对象
        """
        if not self._is_connected or not self._client:
            raise DBInitializationError("Chroma 客户端未连接，请先调用 connect()")

        try:
            # 检查是否已存在
            existing_collections = [c.name for c in self._client.list_collections()]
            if name in existing_collections:
                collection = self._client.get_collection(name=name)
                logger.info(f"已获取存在 collection: {name}")
            else:
                collection = self._client.create_collection(name=name)
                logger.info(f"创建新的 collection: {name}")
            return collection
        except Exception as e:
            logger.error(f"获取或创建 collection 失败: {e}")
            raise


# 全局 Chroma 管理器实例
_chroma_manager: Optional[ChromaManager] = None


async def init_chroma() -> ChromaManager:
    """初始化 Chroma 连接"""
    global _chroma_manager

    if _chroma_manager is None:
        _chroma_manager = ChromaManager()

    if not _chroma_manager.is_connected:
        await _chroma_manager.connect()

    return _chroma_manager


async def close_chroma() -> None:
    """关闭 Chroma 连接"""
    global _chroma_manager

    if _chroma_manager:
        await _chroma_manager.disconnect()
        _chroma_manager = None


def get_chroma_manager() -> ChromaManager:
    """获取 ChromaDB 管理器实例"""
    global _chroma_manager
    if _chroma_manager is None:
        raise DBInitializationError("ChromaDB 管理器未初始化，请先调用 init_chroma()")
    return _chroma_manager


def get_chroma_client() -> Client:
    """获取 Chroma 客户端"""
    return get_chroma_manager().client

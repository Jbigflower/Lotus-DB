"""
LanceDB 连接管理器

提供 LanceDB 客户端的连接管理
仅负责连接管理和底层连接封装，不包含任何数据操作
"""

from typing import Optional, Dict, Any, List
from pathlib import Path

import lancedb
from lancedb import AsyncConnection, AsyncTable

from config.setting import get_settings
from config.logging import get_logger
from src.core.exceptions import (
    DBConnectionError,
    DBConfigurationError,
    DBInitializationError,
    VectorDBError,
    LanceDBError,
    raise_with_context,
)

logger = get_logger(__name__)


class LanceDBManager:
    """LanceDB 向量数据库管理器

    职责：
    - 管理 LanceDB 异步客户端连接
    - 提供客户端初始化和配置
    - 管理表（Table）的获取与创建
    - 不包含任何数据操作或业务逻辑
    """

    def __init__(self):
        self._db: Optional[AsyncConnection] = None  # LanceDB 异步数据库实例
        self._db_settings = get_settings().database
        self._is_connected = False

    async def connect(self) -> None:
        """建立 LanceDB 异步连接"""
        if self._is_connected:
            logger.warning("LanceDB 已经连接，跳过重复连接")
            return

        try:
            db_path = self._db_settings.lancedb_path
            if not db_path:
                raise_with_context(
                    DBConfigurationError("LanceDB 存储路径未配置（lancedb_path）"),
                    context={"db_path": db_path},
                )

            logger.info(f"正在连接 LanceDB: {db_path}")

            # 确保存储目录存在
            db_dir = Path(db_path)
            db_dir.mkdir(parents=True, exist_ok=True)

            # 建立异步连接
            self._db = await lancedb.connect_async(db_path)
            self._is_connected = True
            logger.info(f"LanceDB 连接成功: {db_path}")

        except ValueError as e:
            if "path" in str(e).lower() or "directory" in str(e).lower():
                raise_with_context(
                    DBConfigurationError(f"LanceDB 路径配置错误: {str(e)}"),
                    original_exception=e,
                    context={"db_path": str(db_path)},
                )
            else:
                raise_with_context(
                    LanceDBError(f"LanceDB 配置错误: {str(e)}"),
                    original_exception=e,
                    context={"db_path": str(db_path)},
                )
        except Exception as e:
            raise_with_context(
                DBConnectionError(f"LanceDB 连接失败: {str(e)}"),
                original_exception=e,
                context={"db_path": str(db_path)},
            )

    async def disconnect(self) -> None:
        """断开 LanceDB 连接"""
        if self._db is not None:
            logger.info("正在断开 LanceDB 连接")
            # LanceDB 异步客户端无需显式关闭，释放引用即可
            self._db = None

        self._is_connected = False
        logger.info("LanceDB 连接已断开")

    async def _test_connection(self) -> None:
        """测试连接是否正常"""
        if self._db is None:
            raise DBInitializationError("LanceDB 尚未连接")

        try:
            tables = await self._db.table_names()
            logger.debug(f"LanceDB 可访问表: {tables or '无'}")
        except Exception as e:
            logger.warning(f"LanceDB 测试连接异常（可能是首次使用）: {e}")

    @property
    def db(self) -> AsyncConnection:
        """获取 LanceDB 异步数据库实例"""
        if self._db is None or not self._is_connected:
            raise DBInitializationError("LanceDB 客户端未初始化，请先调用 connect()")
        return self._db

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected

    async def get_or_create_table(
        self, name: str, schema: Optional[Dict] = None, exist_ok: bool = True
    ) -> AsyncTable:
        """
        获取已有表，如果不存在则创建
        Args:
            name: 表名称
            schema: 表结构（创建新表时需要）
            exist_ok: 若表存在且schema不匹配时是否抛出异常
        Returns:
            异步表对象（AsyncTable）
        """
        if not self._is_connected or self._db is None:
            raise DBInitializationError("LanceDB 客户端未连接，请先调用 connect()")

        try:
            # 检查表是否存在
            table_names = await self._db.table_names()
            if name in table_names:
                table = await self._db.open_table(name)
                if schema and not exist_ok and table.schema != schema:
                    raise_with_context(
                        DBConfigurationError(f"表 {name} 已存在且 schema 不匹配"),
                        context={
                            "table_name": name,
                            "existing_schema": str(table.schema),
                            "expected_schema": str(schema),
                        },
                    )
                logger.info(f"已获取存在的表: {name}")
                return table
            else:
                if not schema:
                    raise_with_context(
                        DBConfigurationError(f"创建新表 {name} 时必须提供 schema"),
                        context={"table_name": name},
                    )

                # 创建新表
                table = await self._db.create_table(
                    name=name, schema=schema, exist_ok=exist_ok
                )
                logger.info(f"创建新表: {name}")
                return table
        except Exception as e:
            logger.error(f"获取或创建表 {name} 失败: {e}")
            raise

    async def list_tables(self) -> List[str]:
        """获取所有表名称列表"""
        if not self._is_connected or self._db is None:
            raise DBInitializationError("LanceDB 客户端未连接，请先调用 connect()")
        return await self._db.table_names()

    async def ensure_connected(self):
        """确保连接已建立"""
        if not self._is_connected:
            await self.connect()


# 全局 LanceDB 管理器实例
_lance_manager: Optional[LanceDBManager] = None


async def init_lance() -> LanceDBManager:
    """初始化 LanceDB 连接"""
    global _lance_manager

    if _lance_manager is None:
        _lance_manager = LanceDBManager()

    if not _lance_manager.is_connected:
        await _lance_manager.connect()
        await _lance_manager._test_connection()  # 连接后测试

    return _lance_manager


async def close_lance() -> None:
    """关闭 LanceDB 连接"""
    global _lance_manager

    if _lance_manager:
        await _lance_manager.disconnect()
        _lance_manager = None


def get_lance_manager() -> LanceDBManager:
    """获取 LanceDB 管理器实例"""
    global _lance_manager
    if _lance_manager is None:
        raise DBInitializationError("LanceDB 管理器未初始化，请先调用 init_lance()")
    return _lance_manager


def get_lance_db() -> AsyncConnection:
    """获取 LanceDB 异步实例"""
    return get_lance_manager().db

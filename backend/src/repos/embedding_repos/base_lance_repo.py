from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import pyarrow as pa
from src.db.lance_db import get_lance_manager
from lancedb import AsyncTable

# 新版本 LanceDB 使用 SQL 字符串语法，不需要导入查询操作符
from config.logging import get_logger

logger = get_logger(__name__)


class BaseLanceRepo(ABC):
    """LanceDB 异步抽象仓储层（带批量操作、软删除、日志和异常）"""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.table: Optional[AsyncTable] = None
        self.soft_delete_flag = "is_deleted"

    @property
    def manager(self):
        return get_lance_manager()

    # -------------------------- 异步表绑定 --------------------------
    async def ensure_table_bound(self):
        """确保表已绑定"""
        if not self.table:
            self.table = await self.manager.get_or_create_table(
                self.table_name, schema=self.get_schema()
            )

    # -------------------------- 抽象方法 --------------------------
    @abstractmethod
    def get_schema(self) -> Any:
        """返回 LanceDB 表结构"""
        pass

    @abstractmethod
    async def to_lance_record(self, obj: Any) -> Dict[str, Any]:
        """将对象转换为 LanceDB 插入记录"""
        pass

    @abstractmethod
    async def batch_to_lance_records(self, objs: List[Any]) -> List[Dict[str, Any]]:
        """批量对象转记录"""
        pass

    @abstractmethod
    def from_lance_record(self, record: Dict[str, Any]) -> Any:
        """将 LanceDB 查询结果转换为业务对象"""
        pass

    # -------------------------- 内部工具方法 --------------------------
    def _log_and_raise(self, msg: str, exc: Exception = None):
        logger.error(f"[{self.table_name}] {msg}")
        if exc:
            raise exc
        raise RuntimeError(msg)

    def _build_soft_delete_filter(self, ignore_deleted: bool = False):
        if ignore_deleted:
            return None
        return f"{self.soft_delete_flag} != true"

    def _format_filter_value(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return f"'{value}'"
        return None

    def _build_filter_conditions(
        self, filters: Optional[Dict[str, Any]], ignore_deleted: bool
    ) -> List[str]:
        conditions: List[str] = []
        soft_filter = self._build_soft_delete_filter(ignore_deleted)
        if soft_filter:
            conditions.append(soft_filter)
        if not filters:
            return conditions
        for key, value in filters.items():
            if isinstance(value, list):
                if not value:
                    conditions.append("false")
                    continue
                formatted = []
                for item in value:
                    formatted_value = self._format_filter_value(item)
                    if formatted_value is not None:
                        formatted.append(formatted_value)
                if formatted:
                    conditions.append(f"{key} IN ({', '.join(formatted)})")
                else:
                    conditions.append("false")
                continue
            formatted_value = self._format_filter_value(value)
            if formatted_value is not None:
                conditions.append(f"{key} = {formatted_value}")
        return conditions

    # -------------------------- 基础 CRUD --------------------------
    async def add(self, objs: List[Any]):
        if not objs:
            return
        try:
            await self.ensure_table_bound()
            records = await self.batch_to_lance_records(objs)
            for rec in records:
                rec.setdefault(self.soft_delete_flag, False)
            schema = await self.table.schema()
            data = pa.Table.from_pylist(records, schema=schema)
            await self.table.add(data)
            logger.info(f"[ADD] {len(objs)} 条记录添加到 {self.table_name}")
        except Exception as e:
            self._log_and_raise(f"添加记录失败: {e}", e)

    async def update(self, objs: List[Any]):
        if not objs:
            return
        try:
            await self.ensure_table_bound()
            records = await self.batch_to_lance_records(objs)
            schema = await self.table.schema()
            data = pa.Table.from_pylist(records, schema=schema)
            await self.table.merge_insert("id") \
                .when_matched_update_all() \
                .when_not_matched_insert_all() \
                .execute(data)
            logger.info(f"[UPDATE] {len(objs)} 条记录更新到 {self.table_name}")
        except Exception as e:
            self._log_and_raise(f"更新记录失败: {e}", e)

    async def upsert(self, objs: List[Any]):
        """Alias for update (which performs upsert)"""
        await self.update(objs)

    async def delete(self, ids: List[str], soft: bool = True):
        if not ids:
            return
        try:
            await self.ensure_table_bound()
            if soft:
                id_list = "','".join(ids)
                await self.table.update(
                    updates={self.soft_delete_flag: True}, where=f"id IN ('{id_list}')"
                )
                logger.info(f"[SOFT DELETE] {len(ids)} 条记录软删除: {self.table_name}")
            else:
                id_list = "','".join(ids)
                await self.table.delete(where=f"id IN ('{id_list}')")
                logger.info(f"[DELETE] {len(ids)} 条记录硬删除: {self.table_name}")
        except Exception as e:
            self._log_and_raise(f"删除记录失败: {e}", e)

    async def restore(self, ids: List[str]):
        if not ids:
            return
        try:
            await self.ensure_table_bound()
            id_list = "','".join(ids)
            await self.table.update(
                updates={self.soft_delete_flag: False}, where=f"id IN ('{id_list}')"
            )
            logger.info(f"[RESTORE] {len(ids)} 条记录恢复: {self.table_name}")
        except Exception as e:
            self._log_and_raise(f"恢复记录失败: {e}", e)


    async def get_by_id(self, _id: str, ignore_deleted: bool = False) -> Optional[Any]:
        try:
            await self.ensure_table_bound()
            conditions = [f"id = '{_id}'"]
            soft_filter = self._build_soft_delete_filter(ignore_deleted)
            if soft_filter:
                conditions.append(soft_filter)
            where_clause = " AND ".join(conditions)
            result = await self.table.query().where(where_clause).limit(1).to_list()
            if not result:
                return None
            return self.from_lance_record(result[0].to_dict())
        except Exception as e:
            self._log_and_raise(f"获取记录失败: {e}", e)

    async def count(self, ignore_deleted: bool = False) -> int:
        try:
            await self.ensure_table_bound()
            if ignore_deleted:
                return await self.table.count_rows()
            else:
                result = (
                    await self.table.query()
                    .where(f"{self.soft_delete_flag} != true")
                    .to_list()
                )
                return len(result)
        except Exception as e:
            self._log_and_raise(f"统计记录失败: {e}", e)

    async def clear_all(self, soft: bool = False):
        try:
            await self.ensure_table_bound()
            if soft:
                await self.table.update(
                    updates={self.soft_delete_flag: True},
                    where=self._build_soft_delete_filter(ignore_deleted=True),
                )
            else:
                await self.table.delete(where=None)
            logger.info(f"[CLEAR] 已清空表 {self.table_name} (soft={soft})")
        except Exception as e:
            self._log_and_raise(f"清空记录失败: {e}", e)

    # -------------------------- 向量检索 --------------------------
    async def search(
        self,
        embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        ignore_deleted: bool = False,
    ) -> List[Any]:
        try:
            await self.ensure_table_bound()
            conditions = self._build_filter_conditions(filters, ignore_deleted)
            query = (await self.table.search(embedding)).limit(top_k)
            if conditions:
                where_clause = " AND ".join(conditions)
                query = query.where(where_clause)
            results = await query.to_list()
            objs = []
            for item in results:
                if isinstance(item, dict):
                    record = item
                    record["score"] = item.get("distance", item.get("_distance"))
                else:
                    record = item.to_dict()
                    record["score"] = getattr(item, "distance", None)
                objs.append(self.from_lance_record(record))
            return objs
        except Exception as e:
            self._log_and_raise(f"向量检索失败: {e}", e)

    async def search_with_scores(
        self,
        embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        ignore_deleted: bool = False,
    ) -> List[Tuple[Any, Optional[float]]]:
        try:
            await self.ensure_table_bound()
            conditions = self._build_filter_conditions(filters, ignore_deleted)
            query = (await self.table.search(embedding)).limit(top_k)
            if conditions:
                where_clause = " AND ".join(conditions)
                query = query.where(where_clause)
            results = await query.to_list()
            objs: List[Tuple[Any, Optional[float]]] = []
            for item in results:
                if isinstance(item, dict):
                    record = item
                    score = item.get("distance", item.get("_distance"))
                else:
                    record = item.to_dict()
                    score = getattr(item, "distance", None)
                objs.append((self.from_lance_record(record), score))
            return objs
        except Exception as e:
            self._log_and_raise(f"向量检索失败: {e}", e)

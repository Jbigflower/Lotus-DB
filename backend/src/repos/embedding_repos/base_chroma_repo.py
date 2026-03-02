from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.db.chroma_db import get_chroma_client
from config.logging import get_logger

logger = get_logger(__name__)


class BaseChromaRepo(ABC):
    """Chroma 抽象仓储层（带批量操作、软删除、日志和异常）"""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.client = get_chroma_client()
        # 获取或创建 collection
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.soft_delete_flag = "_is_deleted"

    # -------------------------- 抽象方法 --------------------------
    @abstractmethod
    def to_chroma_record(self, obj: Any) -> Dict[str, Any]:
        """将对象转换为 Chroma 插入记录: id, embedding, metadata, document"""
        pass

    @abstractmethod
    def from_chroma_record(self, record: Dict[str, Any]) -> Any:
        """将 Chroma 查询结果转换为对象"""
        pass

    @abstractmethod
    def batch_to_chroma_records(self, objs: List[Any]) -> List[Dict[str, Any]]:
        """将一批对象转换为可批量生成 embedding 的记录。由子类实现。"""
        pass

    # -------------------------- 内部工具方法 --------------------------
    def _log_and_raise(self, msg: str, exc: Exception = None):
        logger.error(msg)
        if exc:
            raise exc
        raise RuntimeError(msg)

    # -------------------------- 基础增删改查 --------------------------
    def add(self, objs: List[Any]):
        """批量添加"""
        if not objs:
            return
        try:
            ids, embeddings, metadatas, documents = [], [], [], []
            for obj in objs:
                rec = self.to_chroma_record(obj)
                ids.append(rec["id"])
                embeddings.append(rec["embedding"])
                metadatas.append(rec["metadata"])
                documents.append(rec["document"])
            self.collection.add(
                ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
            )
            logger.info(f"[ADD] {len(objs)} 条记录添加到 {self.collection_name}")
        except Exception as e:
            self._log_and_raise(f"[ADD] 添加记录失败: {e}", e)

    def update(self, objs: List[Any]):
        """批量更新"""
        if not objs:
            return
        try:
            ids, embeddings, metadatas, documents = [], [], [], []
            for obj in objs:
                rec = self.to_chroma_record(obj)
                ids.append(rec["id"])
                embeddings.append(rec["embedding"])
                metadatas.append(rec["metadata"])
                documents.append(rec["document"])
            self.collection.update(
                ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
            )
            logger.info(f"[UPDATE] {len(objs)} 条记录更新到 {self.collection_name}")
        except Exception as e:
            self._log_and_raise(f"[UPDATE] 更新记录失败: {e}", e)

    def delete(self, ids: List[str], soft: bool = True):
        """删除记录，支持软删除"""
        if not ids:
            return
        try:
            if soft:
                # 软删除：更新 metadata 标记 _is_deleted=True
                records = [
                    {"id": _id, "metadata": {self.soft_delete_flag: True}}
                    for _id in ids
                ]
                self.collection.update(
                    ids=[r["id"] for r in records],
                    embeddings=[[]] * len(records),
                    metadatas=[r["metadata"] for r in records],
                    documents=[None] * len(records),
                )
                logger.info(
                    f"[SOFT DELETE] {len(ids)} 条记录软删除: {self.collection_name}"
                )
            else:
                self.collection.delete(ids=ids)
                logger.info(f"[DELETE] {len(ids)} 条记录硬删除: {self.collection_name}")
        except Exception as e:
            self._log_and_raise(f"[DELETE] 删除记录失败: {e}", e)

    def restore(self, ids: List[str]):
        """恢复软删除记录"""
        if not ids:
            return
        try:
            records = [
                {"id": _id, "metadata": {self.soft_delete_flag: False}} for _id in ids
            ]
            self.collection.update(
                ids=[r["id"] for r in records],
                embeddings=[[]] * len(records),
                metadatas=[r["metadata"] for r in records],
                documents=[None] * len(records),
            )
            logger.info(f"[RESTORE] {len(ids)} 条记录恢复: {self.collection_name}")
        except Exception as e:
            self._log_and_raise(f"[RESTORE] 恢复记录失败: {e}", e)

    def upsert(self, objs: List[Any]):
        """批量 upsert（存在更新，不存在添加）"""
        if not objs:
            return
        try:
            ids = [obj.id for obj in objs]
            # 简单逻辑：先删除已存在的软删除标记，再 add/update
            existing_ids = (
                [rec["id"] for rec in self.collection.query(ids=ids)["ids"][0]]
                if ids
                else []
            )
            to_update = [obj for obj in objs if obj.id in existing_ids]
            to_add = [obj for obj in objs if obj.id not in existing_ids]
            if to_update:
                self.update(to_update)
            if to_add:
                self.add(to_add)
            logger.info(f"[UPSERT] {len(objs)} 条记录 upsert 到 {self.collection_name}")
        except Exception as e:
            self._log_and_raise(f"[UPSERT] upsert 失败: {e}", e)

    def get_by_id(self, _id: str, ignore_deleted: bool = False) -> Optional[Any]:
        """根据 id 获取记录"""
        try:
            result = self.collection.query(ids=[_id], n_results=1)
            if not result["ids"][0]:
                return None
            metadata = result["metadatas"][0][0]
            if not ignore_deleted and metadata.get(self.soft_delete_flag, False):
                return None
            record = {
                "id": _id,
                "embedding": result["embeddings"][0][0],
                "metadata": metadata,
                "document": result["documents"][0][0],
            }
            return self.from_chroma_record(record)
        except Exception as e:
            self._log_and_raise(f"[GET] 获取记录失败: {e}", e)

    def count(self, ignore_deleted: bool = False) -> int:
        """统计记录数量"""
        try:
            result = self.collection.query(n_results=0)
            if ignore_deleted:
                return len(result["ids"][0])
            else:
                count = sum(
                    1
                    for m in result["metadatas"][0]
                    if not m.get(self.soft_delete_flag, False)
                )
                return count
        except Exception as e:
            self._log_and_raise(f"[COUNT] 统计记录失败: {e}", e)

    def clear_all(self, soft: bool = False):
        """清空所有记录"""
        try:
            if soft:
                ids = result_ids = self.collection.query(n_results=0)["ids"][0]
                self.delete(ids, soft=True)
            else:
                self.collection.delete()
            logger.info(
                f"[CLEAR] 已清空 collection {self.collection_name} (soft={soft})"
            )
        except Exception as e:
            self._log_and_raise(f"[CLEAR] 清空记录失败: {e}", e)

    # -------------------------- 向量检索 --------------------------
    def search(
        self,
        embedding: List[float],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        ignore_deleted: bool = False,
    ) -> List[Any]:
        """向量检索"""
        try:
            where = filters or {}
            if not ignore_deleted:
                where[self.soft_delete_flag] = False

            result = self.collection.query(
                query_embeddings=[embedding], n_results=top_k, where=where
            )

            objs = []
            for i, _id in enumerate(result["ids"][0]):
                record = {
                    "id": _id,
                    "embedding": embedding,
                    "metadata": result["metadatas"][0][i],
                    "document": result["documents"][0][i],
                    "score": result["distances"][0][i],
                }
                objs.append(self.from_chroma_record(record))
            return objs
        except Exception as e:
            self._log_and_raise(f"[SEARCH] 检索失败: {e}", e)

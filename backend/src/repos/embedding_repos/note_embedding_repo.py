from typing import Dict, Any, List, Optional
from lancedb.pydantic import Vector, LanceModel
from pydantic import BaseModel
from src.models import NoteInDB
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo
from src.clients.ollama_embedding_client import iter_get_text_embedding
from config.logging import get_logger

logger = get_logger(__name__)

NOTE_EMBEDDING_DIM = 1024
CHUNK_SIZE = 500  # 每个 chunk 最大字符数（可按token调整）


class NoteSchema(LanceModel):
    """Note embedding schema for LanceDB"""

    id: str  # chunk唯一ID，可用 parent_id + index 拼接
    vector: Vector(dim=NOTE_EMBEDDING_DIM)
    document: str  # chunk文本
    parent_id: str  # 对应原始Note ID
    chunk_index: int  # chunk序号
    user_id: str  # 用户ID
    movie_id: str
    is_public: bool
    is_deleted: bool


class NoteChunk(BaseModel):
    id: str
    parent_id: str
    chunk_index: int
    user_id: str
    movie_id: str
    is_public: bool
    content: str
    is_deleted: bool = False
    score: Optional[float] = None


class NoteEmbeddingRepo(BaseLanceRepo):
    """用户笔记向量化仓储层：支持自动分块、添加、更新、搜索、软删除"""

    def __init__(self):
        super().__init__(table_name="notes")

    # -------------------------- LanceDB表结构 --------------------------
    def get_schema(self) -> NoteSchema:
        """定义LanceDB表结构"""
        return NoteSchema

    # -------------------------- 文本分块 --------------------------
    def _split_text_into_chunks(self, text: str) -> List[str]:
        """将长文本按 CHUNK_SIZE 拆分为多个chunk"""  # TODO: 重叠 + 章节结构: 内容 + 章节标题
        if not text:
            return []
        chunks = [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        return chunks

    # -------------------------- 单条Note转换 --------------------------
    async def to_lance_record(self, note: NoteInDB) -> Dict[str, Any]:
        records = await self.to_lance_records(note)
        return records[0] if records else {}

    async def to_lance_records(self, note: NoteInDB) -> List[Dict[str, Any]]:
        """
        将 NoteInDB 转为多个 LanceDB 记录（分块处理）
        每个 chunk 生成 embedding，记录 chunk_index 和 parent_id
        """
        try:
            chunks = self._split_text_into_chunks(note.content)
            if not chunks:
                return []

            # 生成所有 chunk 的 embedding
            embeddings = []
            async for start_idx, batch_vectors in iter_get_text_embedding(chunks):
                end_idx = start_idx + len(batch_vectors)
                embeddings[start_idx:end_idx] = batch_vectors

            records = []
            for idx, chunk_text in enumerate(chunks):
                vector = embeddings[idx] if embeddings else [0.0] * NOTE_EMBEDDING_DIM
                record_id = f"{note.id}_{idx}"  # chunk唯一ID
                records.append(
                    {
                        "id": record_id,
                        "vector": vector,
                        "document": chunk_text,
                        "parent_id": note.id,
                        "chunk_index": idx,
                        "user_id": note.user_id,
                        "movie_id": note.movie_id,
                        "is_public": note.is_public,
                        "is_deleted": False,
                    }
                )

            return records

        except Exception as e:
            logger.error(f"[TO LANCE RECORDS] Note向量化失败: {e}, NoteID={note.id}")
            raise

    # -------------------------- 批量处理 --------------------------
    async def batch_to_lance_records(
        self, notes: List[NoteInDB]
    ) -> List[Dict[str, Any]]:
        """
        批量将 NoteInDB 列表转换为 LanceDB 记录（含分块）
        优化点：可在 Service 层先收集所有 chunk 再批量生成 embedding
        """
        if not notes:
            return []

        all_chunks = []
        metadata_list = []
        for note in notes:
            chunks = self._split_text_into_chunks(note.content)
            for idx, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                metadata_list.append(
                    {
                        "parent_id": note.id,
                        "chunk_index": idx,
                        "user_id": note.user_id,
                        "movie_id": note.movie_id,
                        "is_public": note.is_public,
                    }
                )

        logger.info(f"总共待生成 embedding chunk 数量：{len(all_chunks)}")
        # 生成 embedding
        vectors = [[0.0] * NOTE_EMBEDDING_DIM for _ in all_chunks]
        async for start_idx, batch_vectors in iter_get_text_embedding(all_chunks):
            end_idx = start_idx + len(batch_vectors)
            vectors[start_idx:end_idx] = batch_vectors

        # 组装 LanceDB 记录
        records = []
        for idx, (chunk_text, vector, meta) in enumerate(
            zip(all_chunks, vectors, metadata_list)
        ):
            record_id = f"{meta['parent_id']}_{meta['chunk_index']}"
            records.append(
                {
                    "id": record_id,
                    "vector": vector,
                    "document": chunk_text,
                    "parent_id": meta["parent_id"],
                    "chunk_index": meta["chunk_index"],
                    "user_id": meta["user_id"],
                    "movie_id": meta["movie_id"],
                    "is_public": meta["is_public"],
                    "is_deleted": False,
                }
            )

        logger.info(f"批量生成 Note LanceDB 记录完成，共 {len(records)} 条")
        return records

    # -------------------------- 批量删除（按 parent_id） --------------------------
    async def delete_by_parent_ids(
        self, parent_ids: List[str], soft: bool = True
    ) -> None:
        """按 parent_id 批量删除所有分块记录。soft=True 为软删除。"""
        await self.ensure_table_bound()
        if not parent_ids:
            return

        # Create comma-separated string of parent_ids for SQL IN clause
        id_list = "', '".join(parent_ids)

        if soft:
            await self.table.update(
                updates={self.soft_delete_flag: True},
                where=f"parent_id IN ('{id_list}')",
            )
        else:
            await self.table.delete(where=f"parent_id IN ('{id_list}')")

    # -------------------------- 从 LanceDB 记录还原 --------------------------
    def from_lance_record(self, record: Dict[str, Any]) -> NoteChunk:
        """将 LanceDB chunk 记录还原为 NoteInDB（仅基础信息）"""
        try:
            return NoteChunk(
                id=record.get("id", record.get("parent_id")),
                parent_id=record.get("parent_id", record.get("id")),
                chunk_index=record.get("chunk_index", 0),
                user_id=record.get("user_id", ""),
                movie_id=record.get("movie_id", ""),
                is_public=record.get("is_public", False),
                content=record.get("document", ""),
                is_deleted=record.get("is_deleted", False),
                score=record.get("score"),
            )
        except Exception as e:
            logger.error(
                f"[FROM LANCE RECORD] 解析Note记录失败: {e}, RecordID={record.get('id')}"
            )
            raise

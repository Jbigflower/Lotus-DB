from typing import Dict, Any, List, Optional
from lancedb.pydantic import Vector, LanceModel
from pydantic import BaseModel
from src.models import AssetInDB
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo
from src.clients.ollama_embedding_client import (
    get_text_embedding_async,
    iter_get_text_embedding,
)
from config.logging import get_logger

logger = get_logger(__name__)

SUBTITLE_EMBEDDING_DIM = 1024
CHUNK_SIZE = 500  # 每个 chunk 最大字符数


class SubtitleSchema(LanceModel):
    """Subtitle embedding schema for LanceDB"""

    id: str  # chunk唯一ID，可用 parent_id + index 拼接
    vector: Vector(dim=SUBTITLE_EMBEDDING_DIM)
    document: str  # chunk文本
    parent_id: str  # 对应原始Subtitle ID
    chunk_index: int  # chunk序号
    movie_id: str  # 所属电影ID
    library_id: str
    start_time: float  # 原始字幕开始时间（秒）
    end_time: float  # 原始字幕结束时间（秒）
    is_deleted: bool


class SubtitleChunk(BaseModel):
    id: str
    parent_id: str
    chunk_index: int
    movie_id: str
    library_id: str
    content: str
    start_time: float
    end_time: float
    is_deleted: bool = False
    score: Optional[float] = None


class SubtitleEmbeddingRepo(BaseLanceRepo):
    """字幕向量化仓储层：支持自动分块、添加、更新、搜索、软删除"""

    def __init__(self):
        super().__init__(table_name="subtitles")

    # -------------------------- LanceDB表结构 --------------------------
    def get_schema(self) -> SubtitleSchema:
        """定义LanceDB表结构"""
        return SubtitleSchema

    # -------------------------- 文本分块 --------------------------
    def _split_text_into_chunks(self, text: str) -> List[str]:
        """将长字幕文本按 CHUNK_SIZE 拆分"""
        if not text:
            return []
        chunks = [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        return chunks

    def _get_value(self, obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _get_text(self, obj: Any) -> str:
        text = self._get_value(obj, "content")
        if text:
            return text
        text = self._get_value(obj, "text")
        if text:
            return text
        text = self._get_value(obj, "description")
        return text or ""

    # -------------------------- 单条Subtitle转换 --------------------------
    async def to_lance_record(self, subtitle: AssetInDB) -> Dict[str, Any]:
        records = await self.to_lance_records(subtitle)
        return records[0] if records else {}

    async def to_lance_records(self, subtitle: AssetInDB) -> List[Dict[str, Any]]:
        """
        将 AssetInDB 转为多个 LanceDB 记录（分块处理）
        """
        try:
            text = self._get_text(subtitle)
            chunks = self._split_text_into_chunks(text)
            if not chunks:
                return []

            embeddings = []
            async for start_idx, batch_vectors in iter_get_text_embedding(chunks):
                end_idx = start_idx + len(batch_vectors)
                embeddings[start_idx:end_idx] = batch_vectors

            records = []
            for idx, chunk_text in enumerate(chunks):
                vector = (
                    embeddings[idx] if embeddings else [0.0] * SUBTITLE_EMBEDDING_DIM
                )
                parent_id = self._get_value(subtitle, "id")
                movie_id = self._get_value(subtitle, "movie_id", "")
                library_id = self._get_value(subtitle, "library_id", "")
                start_time = self._get_value(subtitle, "start_time", 0.0) or 0.0
                end_time = self._get_value(subtitle, "end_time", 0.0) or 0.0
                record_id = f"{parent_id}_{idx}"
                records.append(
                    {
                        "id": record_id,
                        "vector": vector,
                        "document": chunk_text,
                        "parent_id": parent_id,
                        "chunk_index": idx,
                        "movie_id": movie_id,
                        "library_id": library_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "is_deleted": False,
                    }
                )

            return records

        except Exception as e:
            logger.error(
                f"[TO LANCE RECORDS] Subtitle向量化失败: {e}, SubtitleID={subtitle.id}"
            )
            raise

    # -------------------------- 批量处理 --------------------------
    async def batch_to_lance_records(
        self, subtitles: List[AssetInDB]
    ) -> List[Dict[str, Any]]:
        """批量将 AssetInDB 转为 LanceDB 记录（含分块）"""
        if not subtitles:
            return []

        all_chunks = []
        metadata_list = []
        for subtitle in subtitles:
            text = self._get_text(subtitle)
            chunks = self._split_text_into_chunks(text)
            for idx, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                parent_id = self._get_value(subtitle, "id")
                metadata_list.append(
                    {
                        "parent_id": parent_id,
                        "chunk_index": idx,
                        "movie_id": self._get_value(subtitle, "movie_id", ""),
                        "library_id": self._get_value(subtitle, "library_id", ""),
                        "start_time": self._get_value(subtitle, "start_time", 0.0)
                        or 0.0,
                        "end_time": self._get_value(subtitle, "end_time", 0.0) or 0.0,
                    }
                )

        logger.info(f"总共待生成 embedding chunk 数量：{len(all_chunks)}")
        vectors = [[0.0] * SUBTITLE_EMBEDDING_DIM for _ in all_chunks]
        async for start_idx, batch_vectors in iter_get_text_embedding(all_chunks):
            end_idx = start_idx + len(batch_vectors)
            vectors[start_idx:end_idx] = batch_vectors

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
                    "movie_id": meta["movie_id"],
                    "library_id": meta["library_id"],
                    "start_time": meta["start_time"],
                    "end_time": meta["end_time"],
                    "is_deleted": False,
                }
            )

        logger.info(f"批量生成 Subtitle LanceDB 记录完成，共 {len(records)} 条")
        return records

    async def delete_by_parent_ids(
        self, parent_ids: List[str], soft: bool = True
    ) -> None:
        await self.ensure_table_bound()
        if not parent_ids:
            return

        id_list = "', '".join(parent_ids)
        if soft:
            await self.table.update(
                updates={self.soft_delete_flag: True},
                where=f"parent_id IN ('{id_list}')",
            )
        else:
            await self.table.delete(where=f"parent_id IN ('{id_list}')")

    # -------------------------- 从 LanceDB 记录还原 --------------------------
    def from_lance_record(self, record: Dict[str, Any]) -> SubtitleChunk:
        """将 LanceDB chunk 记录还原为 SubtitleChunk（仅基础信息）"""
        try:
            return SubtitleChunk(
                id=record.get("id", record.get("parent_id")),
                parent_id=record.get("parent_id", record.get("id")),
                chunk_index=record.get("chunk_index", 0),
                movie_id=record.get("movie_id", ""),
                library_id=record.get("library_id", ""),
                content=record.get("document", ""),
                start_time=record.get("start_time", 0.0) or 0.0,
                end_time=record.get("end_time", 0.0) or 0.0,
                is_deleted=record.get("is_deleted", False),
                score=record.get("score"),
            )
        except Exception as e:
            logger.error(
                f"[FROM LANCE RECORD] 解析Subtitle记录失败: {e}, RecordID={record.get('id')}"
            )
            raise

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from lancedb.pydantic import Vector, LanceModel

from config.setting import get_settings
from src.clients.ollama_embedding_client import get_text_embedding_async
from src.db import get_mongo_db, init_lance, get_lance_manager

from ..llm.provider import LLMClient
from .conflict import ConflictResolver
from .extraction import ExtractionPipeline
from .models import MemoryItem, MemoryStatus
from .retriever import MemoryRetriever
from .store import MemoryStoreFacade


class MemoryLanceSchema(LanceModel):
    """记忆向量表的 LanceDB Schema。"""
    memory_id: str
    vector: Vector(dim=get_settings().llm.ollama_embedding_dim)
    tier: str
    user_id: Optional[str]
    status: str
    category: str


@dataclass
class MemoryRuntime:
    """记忆子系统运行时门面，负责惰性初始化与组件复用。"""
    llm_client: LLMClient
    _store: Optional[MemoryStoreFacade] = None # 记忆存储门面
    _retriever: Optional[MemoryRetriever] = None # 记忆检索器
    _extractor: Optional[ExtractionPipeline] = None # 记忆抽取管道
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock) # 初始化锁
    _embedding_fn: Optional[Callable[[str], Awaitable[List[float]]]] = None # 向量函数

    async def get_store(self) -> MemoryStoreFacade:
        """获取记忆存储门面。"""
        await self._ensure_ready()
        return self._store

    async def get_retriever(self) -> MemoryRetriever:
        """获取记忆检索器。"""
        await self._ensure_ready()
        return self._retriever

    async def get_extractor(self) -> ExtractionPipeline:
        """获取记忆抽取管道。"""
        await self._ensure_ready()
        return self._extractor

    async def get_agent_core_memories(self, limit: int = 10) -> List[MemoryItem]:
        """加载 Agent 核心规则类记忆。"""
        await self._ensure_ready()
        items = await self._store.get_agent_memories(status=MemoryStatus.ACTIVE)
        items.sort(key=self._memory_sort_key, reverse=True)
        return items[:limit]

    async def get_user_profile_memories(self, user_id: str, limit: int = 10) -> List[MemoryItem]:
        """加载用户画像摘要记忆。"""
        await self._ensure_ready()
        items = await self._store.get_user_memories(user_id=user_id, status=MemoryStatus.ACTIVE)
        items.sort(key=self._memory_sort_key, reverse=True)
        return items[:limit]

    async def _ensure_ready(self) -> None:
        """初始化记忆存储与检索组件，仅首次触发。"""
        if self._store and self._retriever and self._extractor:
            return
        async with self._lock:
            if self._store and self._retriever and self._extractor:
                return
            settings = get_settings()
            mongo_db = get_mongo_db()
            await init_lance()
            manager = get_lance_manager()
            table = await manager.get_or_create_table("memories", schema=MemoryLanceSchema)

            async def embed_one(text: str) -> List[float]:
                """为单条文本生成 embedding，维度不足时回退零向量。"""
                vectors = await get_text_embedding_async([text])
                if not vectors:
                    return [0.0] * settings.llm.ollama_embedding_dim
                vector = vectors[0] or []
                if len(vector) != settings.llm.ollama_embedding_dim:
                    return [0.0] * settings.llm.ollama_embedding_dim
                return vector

            self._embedding_fn = embed_one
            store = MemoryStoreFacade(
                mongo_db["memories"],
                table,
                embed_one,
            )
            retriever = MemoryRetriever(store=store, embedding_fn=embed_one)
            resolver = ConflictResolver(store=store, llm_client=self.llm_client, embedding_fn=embed_one)
            extractor = ExtractionPipeline(
                llm_client=self.llm_client,
                store=store,
                conflict_resolver=resolver,
            )
            self._store = store
            self._retriever = retriever
            self._extractor = extractor

    @staticmethod
    def _memory_sort_key(item: MemoryItem) -> tuple:
        """记忆排序权重：置信度、访问频率与最近访问时间。"""
        return (item.confidence, item.access_count, item.last_accessed_at)

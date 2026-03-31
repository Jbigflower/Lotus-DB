# 记忆子系统 bug 修复

## 记忆模型

1. 当前 mongodb & Lancedb 之间的数据存在不对齐，由于我们直接使用 sync 进行 mongodb --> lancedb，因此这里 lancedb 的数据类型需要向 mongodb 对齐。

lotus-db-backend-refactor/src/agent/memory/models.py
lotus-db-backend-refactor/src/agent/memory/runtime.py

```python
class MemoryLanceSchema(LanceModel):
    """记忆向量表的 LanceDB Schema。"""
    memory_id: str
    vector: Vector(dim=get_settings().llm.ollama_embedding_dim)
    tier: str
    user_id: Optional[str]
    status: str
    category: str
```

解决方案：建议将 Lance schema 定义为 Mongo 的“子集镜像”，至少包含所有会参与过滤/路由/排序的字段：

- 主键：memory_id: str（Mongo 同字段）
- 向量：vector: Vector(dim=embedding_dim)
- 分层：tier: str（AGENT/USER/SESSION…）
- 归属：user_id: Optional[str]、session_id: Optional[str]
- 状态：status: str（ACTIVE/ARCHIVED/DELETED…）
- 类别：category: str（如 PROFILE / RULE / FACT / PREFERENCE…）
- 时间与热度：created_at, updated_at, last_accessed_at, access_count（用于 rerank/衰减）
- 索引版本：embedding_version: int（或 str），用于回填/重建策略

要点：Lance 中的字段类型必须与 Mongo 存储时的序列化结果一致（str/float/int/bool/None），避免 “Mongo 是 datetime，但 Lance 是 str” 这种隐式错配。

2. 当前的记忆模型是否匹配我们的业务需求？


## 记忆加载

当前记忆加载过于简单，需要优化。

lotus-db-backend-refactor/src/agent/memory/runtime.py
```python
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
```

lotus-db-backend-refactor/src/agent/memory/store.py
```python
    async def get_user_memories(
        self,
        user_id: str,
        status: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> List[MemoryItem]:
        """获取用户记忆项。"""

        cursor = self._mongo.find(
            {
                "user_id": user_id,
                "status": status.value,
                "tier": MemoryTier.USER.value,
            }
        )
        docs = await cursor.to_list(length=None)
        return [MemoryItem.from_dict(doc) for doc in docs]

    async def get_agent_memories(
        self,
        status: MemoryStatus = MemoryStatus.ACTIVE,
    ) -> List[MemoryItem]:
        """获取 Agent 记忆项。"""
        cursor = self._mongo.find(
            {
                "status": status.value,
                "tier": MemoryTier.AGENT.value,
            }
        )
        docs = await cursor.to_list(length=None)
        return [MemoryItem.from_dict(doc) for doc in docs]
```

按需加载符合我们的需求：
lotus-db-backend-refactor/src/agent/memory/retriever.py
```python
    async def retrieve_for_context(
        self,
        query: str,
        user_id: str,
        session_id: str,
        agent_top_k: int = 5,
        user_top_k: int = 10,
    ) -> AssembledMemory:
        """检索并组装会话、用户与 Agent 记忆。"""

        query_embedding = await self._embedding_fn(query)
        session_memories = await self._store.get_session_memories(session_id)

        user_candidates = await self._store.search_semantic(
            query_embedding=query_embedding,
            tier=MemoryTier.USER,
            user_id=user_id,
            status=MemoryStatus.ACTIVE,
            top_k=user_top_k * 3,
        )
        user_memories = self._rerank_user_memories(user_candidates, user_top_k)
        for mem in user_memories:
            asyncio.create_task(self._store.touch(mem.memory_id))

        agent_memories = await self._store.search_semantic(
            query_embedding=query_embedding,
            tier=MemoryTier.AGENT,
            status=MemoryStatus.ACTIVE,
            top_k=agent_top_k,
        )

        return AssembledMemory(
            session=session_memories,
            user=user_memories,
            agent=agent_memories,
        )
```

解决方案：在初始化会话时，将 Agent-level & User-level 访问频次最多的 k 个抽取……

## 记忆检索

1. 当前 query or 记忆 的向量化方式存在安全隐患，需要修复

lotus-db-backend-refactor/src/agent/memory/runtime.py

```python
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
```

目前 embed_one(text) 直接把任意文本交给 embedding 服务，主要风险与问题：

- 超长输入导致性能/成本/超时/拒绝服务风险
- 文本包含不可控内容（如 base64、巨大 JSON）导致向量质量差
- embedding 维度不一致时直接用零向量，会“污染检索”（大量零向量会相互接近）

解决方案：

  1. 输入标准化：对 query 与 memory_text 做同样的 normalize（去除过长空白、截断、控制字符处理）。
  2. 长度上限：例如按字符或 token 估算截断（保守：字符 2k~4k），超限直接截断并记录 embedding_failed_reason（写 Mongo）。
  3. 失败策略：embedding 失败不要写入 Lance（或标记 embedding_status=FAILED 并在 Lance 过滤掉），而不是回退零向量。
  4. 缓存策略：对 query embedding 做短期缓存（按会话/请求级），减少重复调用。


2. session level 记忆没有很好的处理，我的初步想法是：
    - 每个会话都有一个独立的记忆表，用于存储会话相关的记忆，注意不要和会话中注入的用户 & agent 级记忆搞混了，这个主要是存储会话信息，比如当前进行的任务，已经完成的任务之类。
    - 会话记忆的检索与存储需要在会话上下文中进行，以确保记忆的一致性。
    - 当回话结束时，记忆表将持久化到主记忆表中，当用户继续对话时，会话记忆将从主记忆表中加载。


## 记忆存储

lotus-db-backend-refactor/src/agent/memory/store.py

1. 嵌入向量的抽取应该是由同步服务负责完成，而不是在存储时直接抽取。

解决方案：
    建议在 models.py 明确 MemoryItem 的业务必填字段（例如 text/content/source/metadata），并把 “检索相似度” 作为只读派生字段（例如 similarity_score: Optional[float]），不要混入持久化字典里。
    写入路径不做“在线 embedding”：写入只落 Mongo，embedding 与索引更新交给同步服务（或异步 worker）。

2. touch 更新访问时间与计数 这一函数能否设计为批处理，以提高效率？

解决方案：
    retriever.py 目前对每条命中的用户记忆都 asyncio.create_task(self._store.touch(...))，会产生：
   - 大量小更新（写放大）
   - 高并发下 Mongo 压力大且难以回压

   1. 提供批处理接口：touch_many(memory_ids: List[str], accessed_at: datetime)
   2. 在一次请求内聚合去重后再批量 touch（$in + $inc + $set）
   3. 可选：按采样率触发 touch（例如仅对 top1/top3 触发），或按时间窗（同一 memory_id 1 分钟内只 touch 一次）

3. async def _await_if_needed(value: Any) -> Any 这个函数是搞笑的么？极大降低了代码的可读性，请修改。
4. 提供的相似性查询很奇怪：

```python
    async def search_semantic(
        self,
        query_embedding: List[float],
        tier: MemoryTier,
        user_id: Optional[str] = None,
        status: MemoryStatus = MemoryStatus.ACTIVE,
        top_k: int = 10,
    ) -> List[MemoryItem]:
        """执行语义检索并回填完整记忆项。"""

        filter_expr = f"tier = '{tier.value}' AND status = '{status.value}'"
        if user_id:
            filter_expr = f"{filter_expr} AND user_id = '{user_id}'"

        query = await self._await_if_needed(self._lance.search(query_embedding))
        query = query.where(filter_expr).limit(top_k)
        lance_results = await self._await_if_needed(query.to_list())
        # print(f"[DEBUG] LanceDB search results: {lance_results}")
        ids = [r.get("memory_id") for r in lance_results if r.get("memory_id")]
        similarity_map: Dict[str, float] = {}
        for result in lance_results:
            memory_id = result.get("memory_id")
            if not memory_id:
                continue
            distance = result.get("distance", result.get("_distance", result.get("score")))
            if isinstance(distance, (int, float)):
                similarity_map[str(memory_id)] = 1.0 - float(distance)
        if not ids:
            return []

        cursor = self._mongo.find({"memory_id": {"$in": ids}})
        docs = await cursor.to_list(length=len(ids))
        item_map = {
            str(doc.get("memory_id")): MemoryItem.from_dict(doc) for doc in docs
        }
        ordered_items: List[MemoryItem] = []
        for memory_id in ids:
            item = item_map.get(memory_id)
            if item is None:
                continue
            similarity = similarity_map.get(memory_id)
            if similarity is not None:
                setattr(item, "similarity_score", similarity)
            ordered_items.append(item)
        return ordered_items
```

当前把 distance 转成 similarity = 1 - distance，这在不同 metric 下可能错误（例如 cosine distance / l2 / inner product 的取值范围不同）。
建议：
   1. 明确 Lance 使用的 metric（cosine / l2 / dot），并按 metric 做归一化或直接使用 Lance 返回的 score。
   2. 内部统一字段命名：similarity_score（越大越相似），并在 rerank 阶段结合 recency/access_count 做融合排序。

## 记忆提取

lotus-db-backend-refactor/src/agent/memory/extraction.py

整体函数实现非常奇怪，需要重新设计。



# 记忆子系统功能拓展

1. 为记忆存储 + 记忆检索 提供对应的 function call，供 agent 调用。
    建议提供两个稳定的函数接口（不直接暴露底层 Mongo/Lance 细节）：
    1. memory.search(query, user_id, session_id, top_k_user, top_k_agent, top_k_session, filters?)
    - 返回结构化 AssembledMemory（含来源、相似度、时间、category）
    2. memory.upsert(items, user_id, session_id, tier, category, source, metadata?)
    - 写 Mongo，返回 memory_id 列表（embedding 异步）

2. 升级 session level 记忆的存储与检索，在 agent loop 中添加 session-level 的记忆管理模块




from typing import Any, Dict, List, Optional, Union, Tuple
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo
from src.logic.rag.reranker_logic import BaseReRanker
import math
import pyarrow as pa
import asyncio
from concurrent.futures import ThreadPoolExecutor

class HybridSearcher:
    def __init__(self, repo: BaseLanceRepo):
        self.repo = repo
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def search(
        self,
        text: str,
        vector: Optional[List[float]] = None,
        mode: str = "hybrid",  # dense, sparse, hybrid
        reranker: Optional[BaseReRanker] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Perform search with specified mode.
        """
        await self.repo.ensure_table_bound()
        
        # Prepare filters
        conditions = self.repo._build_filter_conditions(filters, ignore_deleted=False)
        where_clause = " AND ".join(conditions) if conditions else None
        
        vector_table = None
        fts_table = None
        
        # 1. Vector Search
        if mode in ["dense", "hybrid"] and vector:
            builder = await self.repo.table.search(vector, query_type="vector")
            if where_clause:
                builder = builder.where(where_clause)
            builder = builder.limit(top_k * 5) # Fetch more for re-ranking
            vector_table = await builder.to_arrow()

        # 2. FTS Search
        if mode in ["sparse", "hybrid"] and text:
            try:
                builder = await self.repo.table.search(text, query_type="fts")
                if where_clause:
                    builder = builder.where(where_clause)
                builder = builder.limit(top_k * 5)
                fts_table = await builder.to_arrow()
            except Exception as e:
                pass

        # 3. Rerank or Merge
        final_table = None
        
        if reranker and mode == "hybrid":
             # Use reranker to merge and rank
             # We run it in executor to avoid blocking if it's CPU bound or Sync IO
             loop = asyncio.get_running_loop()
             # Note: rerank_hybrid expects tables, returns table
             # If one table is missing (e.g. FTS failed), handle it.
             v_t = vector_table if vector_table else pa.Table.from_pylist([], schema=await self.repo.table.schema())
             f_t = fts_table if fts_table else pa.Table.from_pylist([], schema=await self.repo.table.schema())
             
             final_table = await loop.run_in_executor(
                 self._executor,
                 reranker.rerank_hybrid,
                 text,
                 v_t,
                 f_t
             )
        else:
            # Manual Merge (RRF or Weighted Sum)
            # If dense only
            if mode == "dense":
                final_table = vector_table
            elif mode == "sparse":
                final_table = fts_table
            elif mode == "hybrid":
                # Convert to lists to merge manually
                v_list = vector_table.to_pylist() if vector_table else []
                f_list = fts_table.to_pylist() if fts_table else []
                merged = self._rrf_merge(v_list, f_list, k=rrf_k)
                # Convert back to table? Or just return list.
                # Since we need to format output, we can just use the list.
                # But to keep flow consistent, let's treat merged as final result list
                pass
        
        # 4. Format Output
        formatted = []
        if final_table:
            results = final_table.to_pylist()
            # Sort if needed? Reranker usually sorts.
            # But just in case
            # results.sort(key=lambda x: x.get("score", x.get("_distance", 0)), reverse=True) # Reranker score usually higher is better?
            # CrossEncoder returns score. Distance is lower better.
            # If reranker used, score is usually relevance (higher better).
            # If vector search only, _distance (lower better).
            
            # This is tricky. 
            # If mode=dense, we have _distance.
            # If reranked, we have score.
            
            for item in results:
                obj = self.repo.from_lance_record(item)
                score = item.get("score")
                if score is None:
                     dist = item.get("_distance")
                     if dist is not None:
                         score = 1.0 / (1.0 + dist) # Convert distance to score
                     else:
                         score = 0.0
                formatted.append({"item": obj, "score": score})
        elif mode == "hybrid" and not reranker:
            # Merged list from _rrf_merge
             for item in merged:
                obj = self.repo.from_lance_record(item)
                formatted.append({"item": obj, "score": item.get("score", 0)})
        
        # Sort final
        formatted.sort(key=lambda x: x["score"], reverse=True)
        return formatted[:top_k]

    def _rrf_merge(self, list1, list2, k=60):
        scores = {}
        
        def process(lst):
            for rank, item in enumerate(lst):
                id_val = item.get("id") or item.get("_id")
                if not id_val: continue
                if id_val not in scores:
                    scores[id_val] = {"item": item, "score": 0}
                scores[id_val]["score"] += 1.0 / (k + rank + 1)

        process(list1)
        process(list2)
        
        results = []
        for val in scores.values():
            item = val["item"]
            item["score"] = val["score"]
            results.append(item)
        return results

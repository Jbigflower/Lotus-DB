import asyncio
import time
from typing import Dict, Any, List, Optional
from config.logging import get_service_logger
from config.setting import settings
from src.core.handler import service_handler
from src.models import UserRole

from src.logic import (
    MovieLogic,
    LibraryLogic,
    CollectionLogic,
    MovieAssetLogic,
    UserAssetLogic
)
from src.repos.embedding_repos.note_embedding_repo import NoteEmbeddingRepo
from src.repos.embedding_repos.subtitle_embedding_repo import SubtitleEmbeddingRepo
from src.repos.embedding_repos.movie_embedding_repo import MovieEmbeddingRepo
from src.clients.ollama_embedding_client import get_text_embedding_async

from src.logic.rag.query_rewriter_logic import QueryRewriterFactory
from src.logic.rag.searcher_logic import HybridSearcher
from src.logic.rag.reranker_logic import BaseReRanker, CrossEncoderReRanker, OllamaEncoderReranker

logger = get_service_logger("rag_search")

class RagSearchService:
    def __init__(self) -> None:
        self.movie_logic = MovieLogic()
        self.library_logic = LibraryLogic()
        self.user_asset_logic = UserAssetLogic()
        self.movie_asset_logic = MovieAssetLogic()
        
        self.note_repo = NoteEmbeddingRepo()
        self.subtitle_repo = SubtitleEmbeddingRepo()
        self.movie_repo = MovieEmbeddingRepo()
        
        self.note_searcher = HybridSearcher(self.note_repo)
        self.subtitle_searcher = HybridSearcher(self.subtitle_repo)
        self.movie_searcher = HybridSearcher(self.movie_repo)
        
        self.logger = logger

    async def _get_accessible_library_ids(
        self, role: UserRole, user_id: Optional[str], only_me: bool
    ) -> List[str]:
        # Reuse logic from SearchService or LibraryLogic
        limit = settings.performance.max_query_limit
        if role == UserRole.ADMIN:
            return []
        if role == UserRole.USER:
            libs_page = await self.library_logic.list_libraries(
                role=UserRole.USER,
                user_id=user_id,
                only_me=only_me,
                page=1,
                page_size=limit,
                query=None,
            )
        else:
            libs_page = await self.library_logic.list_libraries(
                role=UserRole.GUEST,
                user_id=None,
                only_me=None,
                page=1,
                page_size=limit,
                query=None,
            )
        return [lib.id for lib in libs_page.items]

    @service_handler(action="rag_search")
    async def search(
        self,
        *,
        query: str,
        page: int = 1,
        size: int = 20,
        types: Optional[List[str]] = None,
        
        # Rewrite Config
        enable_rewrite: bool = False,
        rewrite_type: str = "llm",
        
        # Search Config
        search_mode: str = "hybrid", # dense, sparse, hybrid
        top_k: int = 20,
        
        # Rerank Config
        enable_rerank: bool = False,
        rerank_type: str = "cross_encoder", # cross_encoder, ollama
        
        # Filters
        only_me: bool = False,
        current_user=None,
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        role = getattr(current_user, "role", UserRole.GUEST)
        user_id = getattr(current_user, "id", None)
        requested_types = types or ["movies", "notes", "subtitles"]

        # 1. Query Rewrite
        rewrite_res = {"original": query, "rewritten": query}
        if enable_rewrite:
            rewriter = QueryRewriterFactory.create_rewriter(rewrite_type)
            if rewriter:
                try:
                    rewrite_res = await rewriter.rewrite(query)
                    # Support MultiQuery? 
                    # If multi_query, rewrite_res['queries'] exists.
                    # For simplicity, we assume single rewritten query in 'rewritten' or use original if complex.
                    # TODO: Handle multi-query loop.
                except Exception as e:
                    self.logger.error(f"Rewrite failed: {e}")

        final_query = rewrite_res.get("rewritten", query)
        # If MultiQuery, final_query might be list. Handle?
        queries = [final_query]
        if "queries" in rewrite_res and isinstance(rewrite_res["queries"], list):
            queries = rewrite_res["queries"]
            
        # 2. Embedding (for Dense/Hybrid)
        vectors_map = {} # query -> vector
        if search_mode in ["dense", "hybrid"]:
            # Batch embed all queries
            vs = await get_text_embedding_async(queries)
            for i, q in enumerate(queries):
                vectors_map[q] = vs[i] if vs and i < len(vs) else None

        # 3. Reranker Init
        reranker = None
        if enable_rerank:
            if rerank_type == "cross_encoder":
                reranker = CrossEncoderReRanker()
            elif rerank_type == "ollama":
                reranker = OllamaEncoderReranker()

        # 4. Search Execution
        # We need to search for each query in each requested type
        # And then merge results?
        # If MultiQuery, we have N queries * M types.
        
        access_lib_ids = []
        if role != UserRole.ADMIN:
            access_lib_ids = await self._get_accessible_library_ids(role, user_id, only_me)

        async def search_repo(searcher: HybridSearcher, q: str, vec: List[float], filters: Dict[str, Any]):
            return await searcher.search(
                text=q,
                vector=vec,
                mode=search_mode,
                reranker=reranker,
                top_k=top_k,
                filters=filters
            )

        tasks = []
        
        # Helper to launch search for a repo
        def launch_search(searcher, repo_type):
            filters = {}
            if repo_type == "notes":
                 if role == UserRole.USER:
                     if only_me: filters["user_id"] = user_id
                     # else: user logic in repo handles mine+public. But here we just pass simple filters.
                     # SearchService handled mine+public merging manually.
                     # HybridSearcher takes filters.
                     # If we want mine+public, we need OR filter.
                     # BaseLanceRepo filters are AND.
                     # We might need to run 2 searches for notes (mine and public) and merge if using HybridSearcher.
                     pass 
            elif repo_type in ["movies", "subtitles"]:
                if role != UserRole.ADMIN:
                    filters["library_id"] = access_lib_ids

            # For each query
            for q in queries:
                vec = vectors_map.get(q)
                # Notes Special handling for User role (Mine OR Public)
                if repo_type == "notes" and role == UserRole.USER and not only_me:
                     # 2 searches
                     tasks.append((repo_type, searcher, q, vec, {"user_id": user_id}))
                     tasks.append((repo_type, searcher, q, vec, {"is_public": True}))
                else:
                    # Apply basic filters
                    if repo_type == "notes":
                         if role == UserRole.USER and only_me:
                             filters["user_id"] = user_id
                         elif role == UserRole.GUEST:
                             filters["is_public"] = True
                    
                    tasks.append((repo_type, searcher, q, vec, filters))

        if "movies" in requested_types:
            launch_search(self.movie_searcher, "movies")
        if "notes" in requested_types:
            launch_search(self.note_searcher, "notes")
        if "subtitles" in requested_types:
            launch_search(self.subtitle_searcher, "subtitles")

        # Execute all searches
        # tasks is list of (type, searcher, q, vec, filters)
        futures = []
        for item in tasks:
            futures.append(search_repo(item[1], item[2], item[3], item[4]))
            
        results_list = await asyncio.gather(*futures)
        
        # 5. Aggregation
        # Group by type
        grouped = {"movies": [], "notes": [], "subtitles": []}
        
        for i, res in enumerate(results_list):
            rtype = tasks[i][0]
            grouped[rtype].extend(res)
            
        # Dedup and Sort per type
        final_results = {}
        for rtype, items in grouped.items():
            # Dedup by item ID (assuming item has id)
            seen = set()
            deduped = []
            for it in items:
                # it is {'item': obj, 'score': ...}
                obj = it["item"]
                oid = getattr(obj, "id", None)
                if oid and oid not in seen:
                    seen.add(oid)
                    deduped.append(it)
            
            # Sort
            deduped.sort(key=lambda x: x["score"], reverse=True)
            
            # Pagination happens here or after object resolution?
            # SearchService does resolution then pagination? 
            # SearchService: Rank -> Paginate -> Resolve.
            # We should paginate here to save resolution cost.
            
            start = (page - 1) * size
            end = start + size
            paged_items = deduped[start:end]
            
            final_results[rtype] = {
                "items": paged_items,
                "total": len(deduped),
                "page": page,
                "size": size,
                "pages": (len(deduped) + size - 1) // size if size > 0 else 0
            }

        # 6. Object Resolution (Fetch full objects)
        # This part is same as SearchService logic (build_note_page, etc.)
        # I'll implement simplified version or call helper
        
        # ... (Implementation of resolution similar to SearchService but adapted to new structure)
        # For brevity, I will assume we return the chunks/refs with scores, and frontend/client resolves, 
        # OR I must implement it to match API contract.
        # The user wants "Refactor NS-Search". So I should match existing output format.
        
        resolved_data = {}
        
        # Notes
        if "notes" in requested_types:
            resolved_data["notes"] = await self._resolve_notes(final_results["notes"])
            
        # Subtitles
        if "subtitles" in requested_types:
            resolved_data["subtitles"] = await self._resolve_subtitles(final_results["subtitles"])
            
        # Movies
        if "movies" in requested_types:
            resolved_data["movies"] = await self._resolve_movies(final_results["movies"])

        return {
            "status": "success",
            "query": rewrite_res,
            "data": resolved_data,
            "meta": {
                "page": page,
                "size": size,
                "time_ms": (time.perf_counter() - start_time) * 1000
            }
        }

    async def _resolve_notes(self, page_dict: Dict[str, Any]) -> Dict[str, Any]:
        items = page_dict["items"]
        if not items: return page_dict
        
        # Extract IDs
        # items is list of {'item': NoteInDB, 'score': float}
        # NoteInDB is the chunk object (from LanceDB).
        # Actually NoteEmbeddingRepo returns NoteInDB-like object but with chunk info.
        
        chunk_ids = [it["item"].id for it in items]
        parent_ids = list(set([it["item"].parent_id for it in items]))
        
        assets = await self.user_asset_logic.get_assets(parent_ids)
        asset_map = {a.id: a for a in assets}
        
        movie_ids = list(set([a.movie_id for a in assets if getattr(a, "movie_id", None)]))
        movies = await self.movie_logic.get_movies(movie_ids)
        movie_map = {m.id: m for m in movies}
        
        resolved_items = []
        for it in items:
            chunk = it["item"]
            note = asset_map.get(chunk.parent_id)
            movie = movie_map.get(note.movie_id) if note else None
            resolved_items.append({
                "chunk": chunk.model_dump() if hasattr(chunk, "model_dump") else chunk,
                "note": note.model_dump() if note else None,
                "movie": movie.model_dump() if movie else None,
                "score": it["score"]
            })
            
        return {**page_dict, "items": resolved_items}

    async def _resolve_subtitles(self, page_dict: Dict[str, Any]) -> Dict[str, Any]:
        items = page_dict["items"]
        if not items: return page_dict
        
        parent_ids = list(set([it["item"].parent_id for it in items]))
        assets = await self.movie_asset_logic.get_assets(parent_ids)
        asset_map = {a.id: a for a in assets}
        
        movie_ids = list(set([a.movie_id for a in assets if getattr(a, "movie_id", None)]))
        movies = await self.movie_logic.get_movies(movie_ids)
        movie_map = {m.id: m for m in movies}
        
        resolved_items = []
        for it in items:
            chunk = it["item"]
            asset = asset_map.get(chunk.parent_id)
            movie = movie_map.get(chunk.movie_id)
            resolved_items.append({
                "chunk": chunk.model_dump() if hasattr(chunk, "model_dump") else chunk,
                "subtitle": asset.model_dump() if asset else None,
                "movie": movie.model_dump() if movie else None,
                "score": it["score"]
            })
        return {**page_dict, "items": resolved_items}

    async def _resolve_movies(self, page_dict: Dict[str, Any]) -> Dict[str, Any]:
        items = page_dict["items"]
        if not items: return page_dict
        
        # items item is MovieChunk (id is movie_id)
        movie_ids = list(set([it["item"].id for it in items]))
        movies = await self.movie_logic.get_movies(movie_ids)
        movie_map = {m.id: m for m in movies}
        
        resolved_items = []
        for it in items:
            chunk = it["item"]
            movie = movie_map.get(chunk.id)
            resolved_items.append({
                "chunk": chunk.model_dump() if hasattr(chunk, "model_dump") else chunk,
                "movie": movie.model_dump() if movie else None,
                "score": it["score"]
            })
        return {**page_dict, "items": resolved_items}


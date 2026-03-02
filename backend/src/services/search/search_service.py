import asyncio
import re
import time
from typing import Optional, Dict, Any, List, Tuple

from config.logging import get_service_logger
from src.core.handler import service_handler
from config.setting import settings
from src.logic import (
    MovieLogic,
    LibraryLogic,
    CollectionLogic,
    MovieAssetLogic,
    UserAssetLogic
)
from src.models import UserRole, LibraryRead, CustomListRead, UserAssetRead
from src.repos.cache_repos.base_redis_repo import BaseRedisRepo
from src.repos.embedding_repos.note_embedding_repo import NoteEmbeddingRepo, NoteChunk
from src.repos.embedding_repos.subtitle_embedding_repo import (
    SubtitleEmbeddingRepo,
    SubtitleChunk,
)
from src.repos.embedding_repos.movie_embedding_repo import MovieEmbeddingRepo, MovieChunk
from src.clients.ollama_embedding_client import get_text_embedding_async

logger = get_service_logger("search_service")


class SearchService:
    def __init__(self) -> None:
        self.movie_logic = MovieLogic()
        self.library_logic = LibraryLogic()
        self.collection_logic = CollectionLogic()
        self.user_asset_logic = UserAssetLogic()
        self.movie_asset_logic = MovieAssetLogic()
        self.note_embedding_repo = NoteEmbeddingRepo()
        self.subtitle_embedding_repo = SubtitleEmbeddingRepo()
        self.movie_embedding_repo = MovieEmbeddingRepo()
        self.cache_repo = BaseRedisRepo(
            namespace="ns_search", default_expire=settings.performance.cache_ttl_seconds
        )
        self.logger = get_service_logger("search_service")

    def _is_admin(self, current_user) -> bool:
        return getattr(current_user, "role", None) == UserRole.ADMIN

    def _is_guest(self, current_user) -> bool:
        return getattr(current_user, "role", None) == UserRole.GUEST

    def _is_user(self, current_user) -> bool:
        return getattr(current_user, "role", None) == UserRole.USER

    def _paginate_dicts(
        self, items: List[Dict[str, Any]], page: int, size: int
    ) -> Dict[str, Any]:
        total = len(items)
        pages = (total + size - 1) // size if size > 0 else 0
        start = max(page - 1, 0) * size
        end = start + size
        return {
            "items": items[start:end],
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        }

    def _union_dedup(
        self,
        items_a: List[Dict[str, Any]],
        items_b: List[Dict[str, Any]],
        key: str = "id",
    ) -> List[Dict[str, Any]]:
        seen = set()
        result: List[Dict[str, Any]] = []
        for it in items_a + items_b:
            k = it.get(key)
            if k not in seen:
                seen.add(k)
                result.append(it)
        return result

    def _to_halfwidth(self, text: str) -> str:
        result = []
        for ch in text:
            code = ord(ch)
            if code == 12288:
                result.append(" ")
            elif 65281 <= code <= 65374:
                result.append(chr(code - 65248))
            else:
                result.append(ch)
        return "".join(result)

    def _normalize_query(self, text: str) -> str:
        text = self._to_halfwidth(text or "")
        text = text.lower()
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_tokens(self, text: str) -> List[str]:
        tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower())
        expanded: List[str] = []
        for tok in tokens:
            expanded.append(tok)
            if re.fullmatch(r"[\u4e00-\u9fff]+", tok) and len(tok) > 1:
                expanded.extend(list(tok))
        return list(dict.fromkeys([t for t in expanded if t]))

    def _rewrite_query(self, query: str) -> Dict[str, Any]:
        normalized = self._normalize_query(query)
        collapsed = normalized.replace(" ", "")
        tokens = self._extract_tokens(normalized)
        variants = list(dict.fromkeys([query, normalized, collapsed]))
        return {
            "raw": query,
            "normalized": normalized,
            "collapsed": collapsed,
            "tokens": tokens,
            "variants": variants,
        }

    def _keyword_score(self, text: str, tokens: List[str]) -> float:
        if not text or not tokens:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for t in tokens if t and t in text_lower)
        return matches / max(len(tokens), 1)

    def _vector_score(self, distance: Optional[float]) -> float:
        if distance is None:
            return 0.0
        return 1.0 / (1.0 + max(distance, 0.0))

    def _rank_chunks(
        self,
        chunks: List[Tuple[Any, Optional[float]]],
        tokens: List[str],
        vector_weight: float,
        keyword_weight: float,
        max_per_parent: int,
        parent_attr: str,
    ) -> List[Dict[str, Any]]:
        ranked: List[Dict[str, Any]] = []
        for chunk, distance in chunks:
            content = getattr(chunk, "content", "")
            vector_score = self._vector_score(distance)
            keyword_score = self._keyword_score(content, tokens)
            final_score = vector_score * vector_weight + keyword_score * keyword_weight
            ranked.append(
                {
                    "chunk": chunk,
                    "vector_score": vector_score,
                    "keyword_score": keyword_score,
                    "score": final_score,
                }
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        if max_per_parent <= 0:
            return ranked
        limited: List[Dict[str, Any]] = []
        counts: Dict[str, int] = {}
        for item in ranked:
            chunk = item["chunk"]
            parent_id = getattr(chunk, parent_attr, None)
            if parent_id is None:
                limited.append(item)
                continue
            count = counts.get(parent_id, 0)
            if count < max_per_parent:
                counts[parent_id] = count + 1
                limited.append(item)
        return limited

    def _build_ns_cache_key(self, payload: Dict[str, Any]) -> str:
        key_body = self.cache_repo.serialize_to_json(payload)
        return f"ns:{hash(key_body)}"

    async def _get_accessible_library_ids(
        self, role: UserRole, user_id: Optional[str], only_me: bool
    ) -> List[str]:
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

    async def _build_note_page(
        self, ranked: List[Dict[str, Any]], page: int, size: int
    ) -> Dict[str, Any]:
        total = len(ranked)
        pages = (total + size - 1) // size if size > 0 else 0
        start = max(page - 1, 0) * size
        end = start + size
        selected = ranked[start:end]
        note_ids = list(
            dict.fromkeys([item["chunk"].parent_id for item in selected])
        )
        assets = await self.user_asset_logic.get_assets(note_ids) if note_ids else []
        asset_map = {a.id: a for a in assets}
        movie_ids = list(
            dict.fromkeys(
                [a.movie_id for a in assets if getattr(a, "movie_id", None)]
            )
        )
        movies = await self.movie_logic.get_movies(movie_ids) if movie_ids else []
        movie_map = {m.id: m for m in movies}
        items: List[Dict[str, Any]] = []
        for item in selected:
            chunk: NoteChunk = item["chunk"]
            note = asset_map.get(chunk.parent_id)
            movie = movie_map.get(note.movie_id) if note else None
            items.append(
                {
                    "chunk": {
                        "id": chunk.id,
                        "parent_id": chunk.parent_id,
                        "chunk_index": chunk.chunk_index,
                        "user_id": chunk.user_id,
                        "movie_id": chunk.movie_id,
                        "is_public": chunk.is_public,
                        "content": chunk.content,
                    },
                    "note": note.model_dump() if note else None,
                    "movie": movie.model_dump() if movie else None,
                    "score": item["score"],
                    "vector_score": item["vector_score"],
                    "keyword_score": item["keyword_score"],
                }
            )
        return {"items": items, "total": total, "page": page, "size": size, "pages": pages}

    async def _build_subtitle_page(
        self, ranked: List[Dict[str, Any]], page: int, size: int
    ) -> Dict[str, Any]:
        total = len(ranked)
        pages = (total + size - 1) // size if size > 0 else 0
        start = max(page - 1, 0) * size
        end = start + size
        selected = ranked[start:end]
        asset_ids = list(
            dict.fromkeys([item["chunk"].parent_id for item in selected])
        )
        assets = await self.movie_asset_logic.get_assets(asset_ids) if asset_ids else []
        asset_map = {a.id: a for a in assets}
        movie_ids = list(
            dict.fromkeys(
                [a.movie_id for a in assets if getattr(a, "movie_id", None)]
            )
        )
        movies = await self.movie_logic.get_movies(movie_ids) if movie_ids else []
        movie_map = {m.id: m for m in movies}
        items: List[Dict[str, Any]] = []
        for item in selected:
            chunk: SubtitleChunk = item["chunk"]
            asset = asset_map.get(chunk.parent_id)
            movie = movie_map.get(chunk.movie_id)
            items.append(
                {
                    "chunk": {
                        "id": chunk.id,
                        "parent_id": chunk.parent_id,
                        "chunk_index": chunk.chunk_index,
                        "movie_id": chunk.movie_id,
                        "library_id": chunk.library_id,
                        "start_time": chunk.start_time,
                        "end_time": chunk.end_time,
                        "content": chunk.content,
                    },
                    "subtitle": asset.model_dump() if asset else None,
                    "movie": movie.model_dump() if movie else None,
                    "score": item["score"],
                    "vector_score": item["vector_score"],
                    "keyword_score": item["keyword_score"],
                }
            )
        return {"items": items, "total": total, "page": page, "size": size, "pages": pages}

    async def _build_movie_page(
        self, ranked: List[Dict[str, Any]], page: int, size: int
    ) -> Dict[str, Any]:
        total = len(ranked)
        pages = (total + size - 1) // size if size > 0 else 0
        start = max(page - 1, 0) * size
        end = start + size
        selected = ranked[start:end]
        
        movie_ids = list(
            dict.fromkeys([item["chunk"].id for item in selected])
        )
        movies = await self.movie_logic.get_movies(movie_ids) if movie_ids else []
        movie_map = {m.id: m for m in movies}
        
        items: List[Dict[str, Any]] = []
        for item in selected:
            chunk: MovieChunk = item["chunk"]
            movie = movie_map.get(chunk.id)
            items.append(
                {
                    "chunk": {
                        "id": chunk.id,
                        "content": chunk.content,
                        "title": chunk.title,
                        "library_id": chunk.library_id,
                    },
                    "movie": movie.model_dump() if movie else None,
                    "score": item["score"],
                    "vector_score": item["vector_score"],
                    "keyword_score": item["keyword_score"],
                }
            )
        return {"items": items, "total": total, "page": page, "size": size, "pages": pages}

    @service_handler(action="global_search")
    async def search(
        self,
        *,
        q: str,
        page: int = 1,
        size: int = 20,
        only_me: bool = False,
        type: str = "summary",
        current_user=None,
    ) -> Dict[str, Any]:
        # 角色判断
        role = getattr(current_user, "role", UserRole.GUEST)
        user_id = getattr(current_user, "id", None)

        def empty_page():
            return {
                "items": [],
                "total": 0,
                "page": page,
                "size": size,
                "pages": 0,
            }

        libraries_dict = empty_page()
        movies_dict = empty_page()
        user_assets_dict = empty_page()
        collections_dict = empty_page()
        movie_assets_dict = empty_page()

        # 1. Libraries (Result)
        if type in ["summary", "libraries"]:
            if self._is_admin(current_user):
                libraries_page = await self.library_logic.list_libraries(
                    role=UserRole.ADMIN,
                    user_id=None,
                    only_me=None,
                    page=page,
                    page_size=size,
                    query=q,
                )
            elif self._is_user(current_user):
                libraries_page = await self.library_logic.list_libraries(
                    role=UserRole.USER,
                    user_id=user_id,
                    only_me=only_me,
                    page=page,
                    page_size=size,
                    query=q,
                )
            else:
                libraries_page = await self.library_logic.list_libraries(
                    role=UserRole.GUEST,
                    user_id=None,
                    only_me=None,
                    page=page,
                    page_size=size,
                    query=q,
                )
            libraries_dict = libraries_page.model_dump()

        # 2. Permissions for Movies (Needed for 'movies' and 'movie_assets')
        permitted_lib_ids = []
        if type in ["summary", "movies", "movie_assets"]:
            if not self._is_admin(current_user):
                # Fetch ALL accessible libraries to determine visibility (ignore q)
                limit = settings.performance.max_query_limit
                if self._is_user(current_user):
                    libs_p = await self.library_logic.list_libraries(
                        role=UserRole.USER,
                        user_id=user_id,
                        only_me=only_me,
                        page=1,
                        page_size=limit,
                        query=None,
                    )
                else:
                    libs_p = await self.library_logic.list_libraries(
                        role=UserRole.GUEST,
                        user_id=None,
                        only_me=None,
                        page=1,
                        page_size=limit,
                        query=None,
                    )
                permitted_lib_ids = [lib.id for lib in libs_p.items]

        # 3. Movies (Result)
        if type in ["summary", "movies"]:
            # 直接使用 library_ids 参数传递允许的库ID，避免 addition_filter 中的 ObjectId 类型问题
            movies_page = await self.movie_logic.list_movies(
                query=q,
                genres=None,
                min_rating=None,
                max_rating=None,
                start_date=None,
                end_date=None,
                tags=None,
                is_deleted=None,
                page=page,
                size=size,
                sort=None,
                addition_filter=None,
                library_ids=permitted_lib_ids if not self._is_admin(current_user) else None,
            )
            movies_dict = movies_page.model_dump()

        # 4. User Assets (Result)
        if type in ["summary", "user_assets"]:
            if self._is_admin(current_user):
                user_assets_page = await self.user_asset_logic.list_assets(
                    query=q,
                    user_id=None,
                    movie_ids=None,
                    asset_type=[],
                    tags=None,
                    is_public=None,
                    page=page,
                    size=size,
                    sort=None,
                    projection=None,
                )
                user_assets_dict = (
                    user_assets_page.model_dump()
                    if hasattr(user_assets_page, "model_dump")
                    else dict(user_assets_page)
                )
            elif self._is_user(current_user):
                if only_me:
                    mine_page = await self.user_asset_logic.list_assets(
                        query=q,
                        user_id=user_id,
                        movie_ids=None,
                        asset_type=[],
                        tags=None,
                        is_public=None,
                        page=page,
                        size=size,
                        sort=None,
                        projection=None,
                    )
                    user_assets_dict = mine_page.model_dump()
                else:
                    mine_page = await self.user_asset_logic.list_assets(
                        query=q,
                        user_id=user_id,
                        movie_ids=None,
                        asset_type=[],
                        tags=None,
                        is_public=None,
                        page=1,
                        size=max(size, 200),
                        sort=None,
                        projection=None,
                    )
                    public_page = await self.user_asset_logic.list_assets(
                        query=q,
                        user_id=None,
                        movie_ids=None,
                        asset_type=[],
                        tags=None,
                        is_public=True,
                        page=1,
                        size=max(size, 200),
                        sort=None,
                        projection=None,
                    )
                    mine_items = [
                        i.model_dump() if hasattr(i, "model_dump") else i
                        for i in mine_page.items
                    ]
                    public_items = [
                        i.model_dump() if hasattr(i, "model_dump") else i
                        for i in public_page.items
                    ]
                    union_items = self._union_dedup(mine_items, public_items, key="id")
                    user_assets_dict = self._paginate_dicts(union_items, page, size)
            else:
                public_page = await self.user_asset_logic.list_assets(
                    query=q,
                    user_id=None,
                    movie_ids=None,
                    asset_type=[],
                    tags=None,
                    is_public=True,
                    page=page,
                    size=size,
                    sort=None,
                    projection=None,
                )
                user_assets_dict = (
                    public_page.model_dump()
                    if hasattr(public_page, "model_dump")
                    else dict(public_page)
                )

        # 5. Collections (Result)
        if type in ["summary", "collections"]:
            if self._is_admin(current_user):
                collections_page = await self.collection_logic.list_collections(
                    user_id=None,
                    role=UserRole.ADMIN,
                    only_me=None,
                    page=page,
                    page_size=size,
                    type_filter=None,
                    query=q,
                )
                collections_dict = collections_page.model_dump()
            elif self._is_user(current_user):
                collections_page = await self.collection_logic.list_collections(
                    user_id=user_id,
                    role=UserRole.USER,
                    only_me=only_me,
                    page=page,
                    page_size=size,
                    type_filter=None,
                    query=q,
                )
                collections_dict = collections_page.model_dump()
            else:
                public_collections_page = await self.collection_logic.list_collections(
                    user_id=None,
                    role=UserRole.GUEST,
                    only_me=None,
                    page=page,
                    page_size=size,
                    type_filter=None,
                    query=q,
                )
                collections_dict = public_collections_page.model_dump()

        # 6. Movie Assets (Result)
        if type in ["summary", "movie_assets"]:
            # Use search_assets directly for asset search, leveraging path/name/metadata search
            # This fixes the issue where searching for asset names failed because it only searched movies first
            movie_assets_page = await self.movie_asset_logic.search_assets(
                query=q,
                page=page,
                size=size,
                library_ids=permitted_lib_ids if not self._is_admin(current_user) else None,
            )
            movie_assets_dict = (
                movie_assets_page.model_dump()
                if hasattr(movie_assets_page, "model_dump")
                else dict(movie_assets_page)
            )

        return {
            "movies": movies_dict,
            "movie_assets": movie_assets_dict,
            "user_assets": user_assets_dict,
            "collections": collections_dict,
            "libraries": libraries_dict,
        }

    @service_handler(action="ns_search")
    async def ns_search(
        self,
        *,
        query: str,
        page: int = 1,
        size: int = 20,
        only_me: bool = False,
        types: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        max_per_parent: int = 2,
        use_cache: bool = False,
        current_user=None,
    ) -> Dict[str, Any]:
        start_time = time.perf_counter()
        role = getattr(current_user, "role", UserRole.GUEST)
        user_id = getattr(current_user, "id", None)
        rewrite_start = time.perf_counter()
        rewrite = self._rewrite_query(query)
        rewrite_ms = (time.perf_counter() - rewrite_start) * 1000
        requested_types = types or ["movies", "notes", "subtitles"]
        cache_key = self._build_ns_cache_key(
            {
                "q": rewrite.get("normalized"),
                "page": page,
                "size": size,
                "only_me": only_me,
                "types": requested_types,
                "top_k": top_k,
                "vector_weight": vector_weight,
                "keyword_weight": keyword_weight,
                "max_per_parent": max_per_parent,
                "role": role,
                "user_id": user_id,
            }
        )
        if use_cache:
            cached = await self.cache_repo.get(cache_key)
            if cached:
                cached.setdefault("meta", {})
                cached["meta"]["cache"] = True
                return cached

        empty_page = {"items": [], "total": 0, "page": page, "size": size, "pages": 0}
        movies_dict: Dict[str, Any] = empty_page
        notes_dict: Dict[str, Any] = empty_page
        subtitles_dict: Dict[str, Any] = empty_page

        access_lib_ids: List[str] = []
        if role != UserRole.ADMIN:
            access_lib_ids = await self._get_accessible_library_ids(role, user_id, only_me)

        need_embedding = "notes" in requested_types or "subtitles" in requested_types or "movies" in requested_types
        embedding = None
        embedding_ms = 0.0
        if need_embedding:
            embedding_start = time.perf_counter()
            vectors = await get_text_embedding_async([rewrite.get("normalized", query)])
            embedding = vectors[0] if vectors else None
            embedding_ms = (time.perf_counter() - embedding_start) * 1000

        top_k_use = top_k or max(size * 5, 20)
        search_ms = 0.0
        rank_ms = 0.0
        assemble_ms = 0.0

        async def search_notes() -> Dict[str, Any]:
            nonlocal search_ms, rank_ms, assemble_ms
            if embedding is None:
                return empty_page
            search_start = time.perf_counter()
            chunks: List[Tuple[Any, Optional[float]]] = []
            if role == UserRole.ADMIN:
                chunks = await self.note_embedding_repo.search_with_scores(
                    embedding, top_k=top_k_use, filters=None
                )
            elif role == UserRole.USER:
                if only_me and user_id:
                    chunks = await self.note_embedding_repo.search_with_scores(
                        embedding, top_k=top_k_use, filters={"user_id": user_id}
                    )
                else:
                    mine = await self.note_embedding_repo.search_with_scores(
                        embedding, top_k=top_k_use, filters={"user_id": user_id}
                    )
                    public = await self.note_embedding_repo.search_with_scores(
                        embedding, top_k=top_k_use, filters={"is_public": True}
                    )
                    merged: Dict[str, Tuple[Any, Optional[float]]] = {}
                    for chunk, score in mine + public:
                        merged[getattr(chunk, "id", None)] = (chunk, score)
                    chunks = list(merged.values())
            else:
                chunks = await self.note_embedding_repo.search_with_scores(
                    embedding, top_k=top_k_use, filters={"is_public": True}
                )
            search_ms += (time.perf_counter() - search_start) * 1000
            rank_start = time.perf_counter()
            ranked = self._rank_chunks(
                chunks,
                rewrite.get("tokens", []),
                vector_weight,
                keyword_weight,
                max_per_parent,
                "parent_id",
            )
            rank_ms += (time.perf_counter() - rank_start) * 1000
            assemble_start = time.perf_counter()
            page_dict = await self._build_note_page(ranked, page, size)
            assemble_ms += (time.perf_counter() - assemble_start) * 1000
            return page_dict

        async def search_subtitles() -> Dict[str, Any]:
            nonlocal search_ms, rank_ms, assemble_ms
            if embedding is None:
                return empty_page
            if role != UserRole.ADMIN and not access_lib_ids:
                return empty_page
            search_start = time.perf_counter()
            filters = None
            if role != UserRole.ADMIN:
                filters = {"library_id": access_lib_ids}
            chunks = await self.subtitle_embedding_repo.search_with_scores(
                embedding, top_k=top_k_use, filters=filters
            )
            search_ms += (time.perf_counter() - search_start) * 1000
            rank_start = time.perf_counter()
            ranked = self._rank_chunks(
                chunks,
                rewrite.get("tokens", []),
                vector_weight,
                keyword_weight,
                max_per_parent,
                "parent_id",
            )
            rank_ms += (time.perf_counter() - rank_start) * 1000
            assemble_start = time.perf_counter()
            page_dict = await self._build_subtitle_page(ranked, page, size)
            assemble_ms += (time.perf_counter() - assemble_start) * 1000
            return page_dict

        async def search_movies() -> Dict[str, Any]:
            nonlocal search_ms, rank_ms, assemble_ms

            if embedding is None:
                return empty_page

            if role != UserRole.ADMIN and not access_lib_ids:
                return empty_page

            search_start = time.perf_counter()
            filters = {}
            if role != UserRole.ADMIN:
                filters["library_id"] = access_lib_ids

            chunks = await self.movie_embedding_repo.search_with_scores(
                embedding, top_k=top_k_use, filters=filters
            )
            search_ms += (time.perf_counter() - search_start) * 1000

            rank_start = time.perf_counter()
            ranked = self._rank_chunks(
                chunks,
                rewrite.get("tokens", []),
                vector_weight,
                keyword_weight,
                max_per_parent,
                "id",
            )
            rank_ms += (time.perf_counter() - rank_start) * 1000

            assemble_start = time.perf_counter()
            page_dict = await self._build_movie_page(ranked, page, size)
            assemble_ms += (time.perf_counter() - assemble_start) * 1000

            return page_dict

        tasks = []
        if "movies" in requested_types:
            tasks.append(search_movies())
        if "notes" in requested_types:
            tasks.append(search_notes())
        if "subtitles" in requested_types:
            tasks.append(search_subtitles())
        results = await asyncio.gather(*tasks) if tasks else []

        idx = 0
        if "movies" in requested_types:
            movies_dict = results[idx]
            idx += 1
        if "notes" in requested_types:
            notes_dict = results[idx]
            idx += 1
        if "subtitles" in requested_types:
            subtitles_dict = results[idx]

        total_ms = (time.perf_counter() - start_time) * 1000
        response = {
            "status": "success",
            "query": rewrite,
            "data": {
                "movies": movies_dict,
                "notes": notes_dict,
                "subtitles": subtitles_dict,
            },
            "meta": {
                "page": page,
                "size": size,
                "cache": False,
                "timing_ms": {
                    "rewrite": rewrite_ms,
                    "embedding": embedding_ms,
                    "search": search_ms,
                    "rank": rank_ms,
                    "assemble": assemble_ms,
                    "total": total_ms,
                },
            },
        }
        if use_cache:
            await self.cache_repo.set(cache_key, response)
        return response

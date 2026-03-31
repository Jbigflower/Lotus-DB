import asyncio
from typing import Optional, Dict, Any, List

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
from src.models import UserRole

logger = get_service_logger("search_service")


class SearchService:
    def __init__(self) -> None:
        self.movie_logic = MovieLogic()
        self.library_logic = LibraryLogic()
        self.collection_logic = CollectionLogic()
        self.user_asset_logic = UserAssetLogic()
        self.movie_asset_logic = MovieAssetLogic()
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

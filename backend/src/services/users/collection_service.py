from typing import List, Optional, Dict, Any
from src.logic import CollectionLogic, MovieLogic
from src.models import (
    CustomListType,
    CustomListCreate,
    CustomListUpdate,
    CustomListRead,
    MovieRead,
    UserRole,
    CustomListPageResult,
)
from src.core.handler import service_handler
from config.logging import get_service_logger
from src.core.exceptions import ForbiddenError


class CollectionService:
    """
    用户片单服务层
    - 处理权限校验、事务与异常转换
    - 委托逻辑层执行核心业务
    - 本模块不涉及 Celery 后台任务
    """

    def __init__(self) -> None:
        self.logic = CollectionLogic()
        self.movie_logic = MovieLogic()
        self.logger = get_service_logger("collection_service")

    async def _ensure_user_not_guest(self, *, current_user) -> None:
        if current_user and getattr(current_user, "role", None) == UserRole.GUEST:
            raise ForbiddenError("访客不可执行此操作")

    async def _ensure_owner_or_public(
        self, read: CustomListRead, *, current_user
    ) -> None:
        if (
            current_user
            and getattr(current_user, "role", None) == UserRole.GUEST
            and (not read.is_public)
        ):
            raise ForbiddenError("访客仅可访问公开合集")
        if current_user and getattr(current_user, "role", None) != UserRole.ADMIN:
            if read.user_id != getattr(current_user, "id", None) and (
                not read.is_public
            ):
                raise ForbiddenError("无权限访问该合集")

    async def _ensure_user_edit_permission(
        self, read: CustomListRead, *, current_user
    ) -> None:
        if current_user.role == UserRole.ADMIN:
            return
        if read.user_id != getattr(current_user, "id", None):
            raise ForbiddenError("不可操作非本人片单")

    @service_handler(action="list_collections")
    async def list_collections(
        self,
        user_id: Optional[str] = None,
        type_filter: Optional[CustomListType] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        *,
        current_user=None,
    ) -> CustomListPageResult:
        role = getattr(current_user, "role", None)
        return await self.logic.list_collections(
            user_id=user_id,
            role=role,
            type_filter=type_filter,
            query=query,
            page=page,
            page_size=page_size,
        )

    @service_handler(action="get_collection")
    async def get_collection(
        self, collection_id: str, *, current_user
    ) -> Optional[CustomListRead]:
        read = await self.logic.get_collection(collection_id)
        if not read:
            return None
        await self._ensure_owner_or_public(read, current_user=current_user)
        return read

    @service_handler(action="create_collection")
    async def create_collection(
        self, data: CustomListCreate, *, current_user
    ) -> CustomListRead:
        await self._ensure_user_not_guest(current_user=current_user)
        if data.user_id:
            if data.user_id != getattr(current_user, "id", None):
                raise ForbiddenError("不可为其他用户创建合集")
        else:
            data.user_id = current_user.id
        created = await self.logic.create_collection(data)
        return created

    @service_handler(action="update_collection")
    async def update_collection(
        self, collection_id: str, data: CustomListUpdate, *, current_user
    ) -> CustomListRead:
        collection = await self.get_collection(collection_id, current_user=current_user)
        if not collection:
            return None
        await self._ensure_user_edit_permission(collection, current_user=current_user)
        # 确认归属或公开
        read = await self.logic.get_collection(collection_id)
        if not read:
            return None
        await self._ensure_owner_or_public(read, current_user=current_user)
        updated = await self.logic.update_collection(collection_id, data)
        return updated

    @service_handler(action="delete_collection")
    async def delete_collection(
        self, collection_id: str, *, current_user
    ) -> CustomListRead:
        collection = await self.get_collection(collection_id, current_user=current_user)
        if not collection:
            return None
        await self._ensure_user_edit_permission(collection, current_user=current_user)
        read = await self.logic.get_collection(collection_id)
        if not read:
            return None
        await self._ensure_owner_or_public(read, current_user=current_user)
        deleted = await self.logic.delete_collection(collection_id)
        return deleted

    @service_handler(action="add_movies")
    async def add_movies(
        self,
        collection_id: str,
        movie_ids: List[str],
        *,
        current_user,
        use_buffer: bool = True,
    ) -> dict:
        collection = await self.get_collection(collection_id, current_user=current_user)
        if not collection:
            return None
        await self._ensure_user_edit_permission(collection, current_user=current_user)
        _ = await self.logic.append_movies(
            collection_id, movie_ids, 
        )
        return {"message": "Movies added successfully"}

    @service_handler(action="remove_movies")
    async def remove_movies(
        self,
        collection_id: str,
        movie_ids: List[str],
        *,
        current_user,
        use_buffer: bool = True,
    ) -> dict:
        collection = await self.get_collection(collection_id, current_user=current_user)
        if not collection:
            return None
        await self._ensure_user_edit_permission(collection, current_user=current_user)
        _ = await self.logic.remove_movies(
            collection_id, movie_ids, 
        )
        return {"message": "Movies removed successfully"}

    @service_handler(action="get_collection_movies")
    async def get_collection_movies(
        self, collection_id: str, *, current_user
    ) -> List[Dict[str, Any]]:
        collection = await self.logic.get_collection(collection_id)
        if not collection:
            return []
        await self._ensure_owner_or_public(collection, current_user=current_user)
        movies = await self.movie_logic.get_movies(collection.movies)
        addition = await self.logic.get_target_collection_with_addtion_items(collection_id, getattr(current_user, "id", None))
        fav_ids = set((addition.get("favorite").movies) if addition.get("favorite") else [])
        watch_ids = set((addition.get("watchlist").movies) if addition.get("watchlist") else [])
        decorated: List[Dict[str, Any]] = []
        for m in movies:
            d = m.model_dump()
            d["is_favoriter"] = m.id in fav_ids
            d["is_watchLater"] = m.id in watch_ids
            decorated.append(d)
        return decorated
    
    @service_handler(action="init_user_default_collections")
    async def init_user_default_collections(
        self, *, current_user
    ) -> List[CustomListRead]:
        await self._ensure_user_not_guest(current_user=current_user)
        return await self.logic.init_default(
            user_id=getattr(current_user, "id", None),
        )

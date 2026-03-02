
from typing import Any, Dict, List, Optional
from config.logging import get_logger
from src.repos.cache_repos.base_redis_repo import DualLayerCache
from src.models import CustomListType


class UserCustomListRedisRepo(DualLayerCache):
    """用户自定义片单 Redis 缓存仓储类
    1、detail 具体的片单内容，key 为片单 id
    2、列表：User_{user_id}，key 为用户 id，value 为用户所有片单 id 列表
    """
    def __init__(self):
        super().__init__(
            namespace="user_custom_lists", 
            default_expire=3600,
            id_field="id",
            settings={
                "detail": 3600,
                "search": 600,
                "state": 600,
                "user": 3600,
            },
            hit_and_refresh=0.2,
            )
        
        self._logger = get_logger(self.__class__.__name__)

    async def get_user_favorite(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            items: Optional[List[Dict[str, Any]]] = await super()._get_item_list("user", user_id)
            if not items:
                return None
            for it in items:
                if (it or {}).get("type") == CustomListType.FAVORITE.value:
                    return it
            return None
        except Exception as e:
            self._logger.error(f"[{self.namespace}] get_user_favorite 异常 user_id={user_id}: {e}")
            return None

    async def get_user_watchlist(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            items: Optional[List[Dict[str, Any]]] = await super()._get_item_list("user", user_id)
            if not items:
                return None
            for it in items:
                if (it or {}).get("type") == CustomListType.WATCHLIST.value:
                    return it
            return None
        except Exception as e:
            self._logger.error(f"[{self.namespace}] get_user_watchlist 异常 user_id={user_id}: {e}")
            return None

    async def get_user_favorite_movie_ids(self, user_id: str) -> List[str]:
        fav = await self.get_user_favorite(user_id)
        return list((fav or {}).get("movies", []) or [])

    async def get_user_watchlist_movie_ids(self, user_id: str) -> List[str]:
        watch = await self.get_user_watchlist(user_id)
        return list((watch or {}).get("movies", []) or [])

    async def refresh_user_cache(self, user_id: str, items: List[Any]) -> bool:
        """刷新用户片单列表缓存"""
        data = [x.model_dump() if hasattr(x, "model_dump") else x for x in items]
        return await self._cache_item_list("user", user_id, data)

    async def clear_user_cache(self, user_id: str) -> bool:
        """清除用户片单列表缓存"""
        return await self.delete_item_list("user", user_id)
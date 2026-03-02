from typing import Any, Dict, List, Optional    
from config.logging import get_logger
from src.repos.cache_repos.base_redis_repo import DualLayerCache


class UserAssetRedisRepo(DualLayerCache):
    """用户资产 Redis 缓存仓储类（用户收藏字幕/自定义标签等"""

    PREFIX_MOVIE_USER = "movie_user"

    def __init__(self):
        super().__init__(
            namespace="user_assets", 
            default_expire=3600,
            id_field="id",
            settings={
                self.PREFIX_DETAIL: 3600,
                self.PREFIX_SEARCH: 600,
                self.PREFIX_STATE: 600,
                self.PREFIX_MOVIE_USER: 3600,
            },
            hit_and_refresh=0.2,
            )
        
        self._logger = get_logger(self.__class__.__name__)


    # ---------------- 列表缓存（ID 列表 + 详情保障）----------------
    async def _cache_movie_list(
        self,
        movie_id: str,
        user_id: str,
        items: List[Dict[str, Any]],
        expire: Optional[int] = None,
    ) -> bool:
        key_suffix = f"{user_id}:{movie_id}"
        return await super()._cache_item_list(
                self.PREFIX_MOVIE_USER, key_suffix, items, expire
            )

    async def _get_movie_list(
        self, movie_id: str, user_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        key_suffix = f"{user_id}:{movie_id}"
        return await super()._get_item_list(
                self.PREFIX_MOVIE_USER, key_suffix
            )
        
    async def delete_movie_list(self, movie_id: str, user_id: str) -> bool:
        """删除列表并按策略批量收敛关联详情 TTL"""
        key_suffix = f"{user_id}:{movie_id}"
        return await super().delete_item_list(
                self.PREFIX_MOVIE_USER, key_suffix
            )

"""任务 Redis 缓存仓储类（轻量版）"""
from src.repos.cache_repos.base_redis_repo import DualLayerCache
from config.logging import get_logger


class TaskRedisRepo(DualLayerCache):
    """任务 Redis 缓存仓储类（轻量版）"""

    def __init__(self):
        super().__init__(
            namespace="task", 
            default_expire=300,
            id_field="id",
            settings={
                "detail": 300,
                "search": 150,
                "state": 150,
            },
            hit_and_refresh=0.2,
            )
        
        self._logger = get_logger(self.__class__.__name__)

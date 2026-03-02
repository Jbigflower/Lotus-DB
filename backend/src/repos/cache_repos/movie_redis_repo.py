"""
电影缓存仓储层
提供电影相关的 Redis 缓存操作，包括详情、搜索、热门、最近添加与统计信息。
"""
from config.logging import get_logger
from src.repos.cache_repos.base_redis_repo import DualLayerCache


class MovieRedisRepo(DualLayerCache):
    """电影 Redis 缓存仓储类"""

    def __init__(self):
        super().__init__(
            namespace="movie",
            default_expire=3600,
            id_field="id",
            settings={
                "detail": 3600,
                "search": 600,
                "state": 600,
                "customList": 3600,
                "recent": 3600,
                "popular": 3600,
            },
        )
        self._logger = get_logger(self.__class__.__name__)
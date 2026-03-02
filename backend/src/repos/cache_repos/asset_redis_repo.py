from config.logging import get_logger
from src.repos.cache_repos.base_redis_repo import DualLayerCache


class AssetRedisRepo(DualLayerCache):
    """电影资产 Redis 缓存仓储类（字幕/海报/预告片等）"""

    def __init__(self):
        super().__init__(namespace="assets", default_expire=3600, id_field="id", settings={
                "detail": 3600,
                "search": 600,
                "state": 600,
                "movie": 3600,
            }, hit_and_refresh=0.2)
        self._logger = get_logger(self.__class__.__name__)
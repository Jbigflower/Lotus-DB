from typing import List, Dict, Any, Optional
from config.logging import get_logger
from src.repos.cache_repos.base_redis_repo import DualLayerCache


class WatchHistoryRedisRepo(DualLayerCache):
    """观看历史 Redis 缓存仓储类
    1、detail 具体的观看记录，key 为记录 id
    2、列表：recent_{user_id}_{limit} key 为用户 id + 最近播放数量，value 为记录 id 列表
    """
    PREFIX_RECENT_USER = "recent"

    def __init__(self):
        super().__init__(
            namespace="watch_history", 
            default_expire=3600,
            id_field="id",
            settings={
                self.PREFIX_DETAIL: 3600,
                self.PREFIX_SEARCH: 600,
                self.PREFIX_STATE: 600,
                self.PREFIX_RECENT_USER: 3600,
            },
            hit_and_refresh=0.2,
            )
        
        self._logger = get_logger(self.__class__.__name__)
    
    # ---------------- 最近播放 ----------------
    async def _cache_recent_list(
        self,
        user_id: str,
        limit: int,
        items: List[Dict[str, Any]],
        expire: Optional[int] = None,
    ) -> bool:
        key_suffix = f'{user_id}_{limit}'
        return await super()._cache_item_list(
                self.PREFIX_RECENT_USER, key_suffix, items, expire
            )
        
    async def _get_recent_list(
        self, user_id: str, limit: int
    ) -> Optional[List[Dict[str, Any]]]:
        key_suffix = f'{user_id}_{limit}'
        return await super()._get_item_list(
                self.PREFIX_RECENT_USER, key_suffix 
            )
        
    async def _delete_recent_list(self, user_id: str) -> bool:   
        """删除列表并按策略批量收敛关联详情 TTL"""
        pattern = self._key(self._list_key(self.PREFIX_RECENT_USER, f"{user_id}_*"))
        deleted = await self._delete_by_pattern(pattern)
        return deleted > 0
        
    async def _update_recent_list(self, user_id: str, watch_history: Dict[str, Any]) -> bool:
        item_id = self._get_item_id(watch_history)
        if not item_id:
            self._logger.warning(f"[{self.namespace}] update_recent_list 缺少有效 id，忽略: {watch_history}")
            return False

        try:
            # 扫描该用户所有 limit 下的列表（采用双命名空间键模式）
            pattern = self._key(self._list_key(self.PREFIX_RECENT_USER, f"{user_id}_*"))
            matched: Dict[int, Dict[str, Any]] = {}

            async for raw_key in self.client.scan_iter(match=pattern):
                namespaced_key = raw_key.decode("utf-8") if isinstance(raw_key, (bytes, bytearray)) else raw_key
                # 解析 limit（key 末段是 <user_id>_<limit>）
                suffix = namespaced_key.split(":")[-1]
                parts = suffix.rsplit("_", 1)
                if len(parts) != 2 or not parts[1].isdigit():
                    continue
                limit = int(parts[1])

                # 获取 TTL 和原列表 ids
                pipe = self.client.pipeline()
                pipe.ttl(namespaced_key)
                pipe.get(namespaced_key)
                ttl, raw_ids = await pipe.execute()

                ids = self._decode_pipeline_value(raw_ids)
                if ids is None or not isinstance(ids, list):
                    ids = []

                matched[limit] = {
                    "namespaced_key": namespaced_key,
                    "key_suffix": suffix,  # <user_id>_<limit>
                    "ttl": ttl,
                    "ids": ids,
                }

            # 如果该用户没有任何 limit 下的列表缓存，直接返回 True
            if not matched:
                return True

            # 以最大 limit 的列表为基准进行更新
            max_limit = max(matched.keys())
            base_ids = list(matched[max_limit]["ids"])  # 拷贝
            if item_id in base_ids:
                base_ids.remove(item_id)
                new_base = [item_id] + base_ids
            else:
                # 新增，先缓存 detail
                await self.cache_detail(watch_history)
                new_base = [item_id] + base_ids

            # 最大列表越界裁剪
            if len(new_base) > max_limit:
                new_base = new_base[:max_limit]

            # 回写所有 limit 列表（按各自 TTL 或默认过期）
            all_ok = True
            for limit, info in matched.items():
                ttl = info["ttl"]
                # ttl > 0 保留原 TTL；否则使用默认策略
                expire = ttl if isinstance(ttl, int) and ttl > 0 else self.settings.get(self.PREFIX_RECENT_USER, self.default_expire)

                target_ids = new_base if len(new_base) <= limit else new_base[:limit]
                list_key = self._list_key(self.PREFIX_RECENT_USER, info["key_suffix"])
                ok = await self.set(list_key, target_ids, expire)
                if not ok:
                    all_ok = False
                    self._logger.warning(f"[{self.namespace}] update_recent_list 写入失败 key={list_key}")

            return all_ok
        except Exception as e:
            self._logger.error(f"[{self.namespace}] update_recent_list 异常 user_id={user_id}: {e}")
            return False
        

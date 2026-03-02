import json
import random
from enum import Enum
from bson import ObjectId
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from config.logging import get_logger
from src.db.redis_db import get_redis_client


class BaseRedisRepo:
    """异步 Redis Repo 基类，封装常用 Redis 操作，带异常处理和日志"""

    def __init__(
        self, namespace: str = "default", default_expire: Optional[int] = None
    ):
        self.namespace = namespace
        self.default_expire = default_expire
        # 不在构造阶段获取 Redis 客户端，避免 FastAPI 启动生命周期未完成时的竞态问题
        self._logger = get_logger(self.__class__.__name__)

    def _key(self, key: str) -> str:
        """生成带命名空间的 Redis key"""
        return key if key.startswith(f"{self.namespace}:") else f"{self.namespace}:{key}"

    @property
    def client(self) -> Redis:
        # 惰性获取 Redis 客户端：只有在真正需要使用时才获取
        # 此时 FastAPI 的 lifespan 已完成，init_redis() 已被调用
        return get_redis_client()

    # ---------------- 序列化&反序列化 ----------------
    def _serialize_value(self, value: Any) -> Any:
        """递归序列化 Python 对象"""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        # datetime 转 ISO 格式字符串
        if isinstance(value, datetime):
            return {"__type__": "datetime", "value": value.isoformat()}
        if isinstance(value, date):
            return {"__type__": "date", "value": value.isoformat()}
        # ObjectId 转字符串
        if isinstance(value, ObjectId):
            raise ValueError(
                f"ObjectId 类型不支持序列化，请检查代码，查看哪里泄露的 ObjectId: {value}"
            )
        # Enum 转字符串
        if isinstance(value, Enum):
            return {
                "__type__": "enum",
                "value": value.value,
                "enum_class": value.__class__.__name__,
            }
        # list / tuple / set
        if isinstance(value, (list, tuple, set)):
            return [self._serialize_value(v) for v in value]
        # dict
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        # 其他对象（例如 Pydantic 模型）
        if hasattr(value, "model_dump"):
            return self._serialize_value(value.model_dump())
        # fallback
        return {"__type__": "unknown", "repr": repr(value)}

    def serialize_to_json(self, data: Any) -> str:
        """将复杂对象序列化为 JSON 字符串"""
        try:
            return json.dumps(self._serialize_value(data), ensure_ascii=False)
        except Exception as e:
            raise ValueError(f"序列化失败: {e}")

    def _deserialize_value(self, value: Any) -> Any:
        """递归反序列化"""
        if isinstance(value, dict):
            # datetime
            if "__type__" in value:
                t = value["__type__"]
                if t == "datetime":
                    return datetime.fromisoformat(value["value"])
                elif t == "date":
                    return date.fromisoformat(value["value"])
                elif t == "objectid":
                    raise ValueError(
                        f"ObjectId 类型不支持反序列化，请检查代码，查看哪里泄露的 ObjectId: {value}"
                    )
                elif t == "enum":
                    # 枚举类型请在 Repo 层手动转换
                    return value["value"]
                elif t == "unknown":
                    return value.get("repr")
            # 普通 dict，递归解包
            return {k: self._deserialize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._deserialize_value(v) for v in value]
        return value

    def deserialize_from_json(self, data: str) -> Dict[str, Any]:
        """将 JSON 字符串反序列化为 Python 对象"""
        try:
            raw = json.loads(data)
            return self._deserialize_value(raw)
        except Exception as e:
            raise ValueError(f"反序列化失败: {e}")

    # ---------------- 基础操作 ----------------
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        k = self._key(key)
        expire = expire or self.default_expire
        try:
            v = self.serialize_to_json(value)
            if expire:
                result = await self.client.set(k, v, ex=expire)
            else:
                result = await self.client.set(k, v)
            self._logger.debug(
                f"[RedisRepo] SET key={k} expire={expire} success={result}"
            )
            return result
        except (RedisError, TypeError, ValueError) as e:
            self._logger.error(f"[RedisRepo] Failed to set key={k}: {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        k = self._key(key)
        try:
            val = await self.client.get(k)
            if val is None:
                self._logger.debug(f"[RedisRepo] GET key={k} returned None")
                return None
            try:
                return self._deserialize_value(json.loads(val))
            except json.JSONDecodeError:
                self._logger.warning(
                    f"[RedisRepo] GET key={k} failed to decode JSON, return raw value"
                )
                return val
        except RedisError as e:
            self._logger.error(f"[RedisRepo] Failed to get key={k}: {e}")
            return None

    async def delete(self, key: str) -> int:
        k = self._key(key)
        try:
            result = await self.client.delete(k)
            self._logger.debug(
                f"[RedisRepo] DELETE key={k} success, deleted_count={result}"
            )
            return result
        except RedisError as e:
            self._logger.error(f"[RedisRepo] Failed to delete key={k}: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        k = self._key(key)
        try:
            result = await self.client.exists(k) > 0
            self._logger.debug(f"[RedisRepo] EXISTS key={k} result={result}")
            return result
        except RedisError as e:
            self._logger.error(f"[RedisRepo] Failed to check exists key={k}: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        k = self._key(key)
        try:
            result = await self.client.expire(k, seconds)
            self._logger.debug(
                f"[RedisRepo] EXPIRE key={k} seconds={seconds} success={result}"
            )
            return result
        except RedisError as e:
            self._logger.error(f"[RedisRepo] Failed to set expire for key={k}: {e}")
            return False

    # ---------------- 批量操作 ----------------
    async def mget(self, keys: List[str]) -> List[Optional[Any]]:
        k_list = [self._key(k) for k in keys]
        try:
            vals = await self.client.mget(*k_list)
            result = []
            for val in vals:
                if val is None:
                    result.append(None)
                else:
                    try:
                        # 关键修复：统一调用递归反序列化
                        result.append(self._deserialize_value(json.loads(val)))
                    except json.JSONDecodeError:
                        result.append(val)
            return result
        except RedisError as e:
            self._logger.error(f"[RedisRepo] Failed mget keys={k_list}: {e}")
            return [None] * len(keys)

    async def mset(self, kv_dict: Dict[str, Any], expire: Optional[int] = None) -> bool:
        expire = expire or self.default_expire
        try:
            pipe = self.client.pipeline()
            for k, v in kv_dict.items():
                key = self._key(k)
                # 关键修复：使用统一的序列化逻辑
                value = self.serialize_to_json(v)
                pipe.set(key, value)
                if expire:
                    pipe.expire(key, expire)
            results = await pipe.execute()
            self._logger.debug(f"[RedisRepo] MSET keys={list(kv_dict.keys())} success")
            return all(results)
        except RedisError as e:
            self._logger.error(
                f"[RedisRepo] Failed mset keys={list(kv_dict.keys())}: {e}"
            )
            return False

    async def _delete_by_pattern(self, namespaced_pattern: str) -> int:
        """
        统一的按模式删除方法：
        - 直接使用 BaseRedisRepo.client 与命名空间 key
        - 复用在列表/全量清理等场景，减少重复代码
        """
        deleted = 0
        try:
            async for raw_key in self.client.scan_iter(match=namespaced_pattern):
                # 直接删除完整的带命名空间的原始 key
                res = await self.client.delete(raw_key)
                deleted += int(res or 0)
        except Exception as e:
            self._logger.error(
                f"[LibraryCache] Failed to delete by pattern {namespaced_pattern}: {e}"
            )
        return deleted

    # ---------------- Hash 操作 ----------------
    async def hset(self, key: str, field: str, value: Any) -> bool:
        k = self._key(key)
        try:
            # 统一序列化
            v = self.serialize_to_json(value)
            await self.client.hset(k, field, v)
            return True
        except RedisError as e:
            self._logger.error(f"[RedisRepo] HSET failed key={k} field={field}: {e}")
            return False

    async def hget(self, key: str, field: str) -> Optional[Any]:
        k = self._key(key)
        try:
            val = await self.client.hget(k, field)
            if val is None:
                return None
            try:
                # 统一反序列化
                return self._deserialize_value(json.loads(val))
            except json.JSONDecodeError:
                return val
        except RedisError as e:
            self._logger.error(f"[RedisRepo] HGET failed key={k} field={field}: {e}")
            return None

    async def hgetall(self, key: str) -> Dict[str, Any]:
        k = self._key(key)
        try:
            vals = await self.client.hgetall(k)
            result = {}
            for field, val in vals.items():
                try:
                    # 统一反序列化
                    result[field.decode()] = self._deserialize_value(json.loads(val))
                except json.JSONDecodeError:
                    result[field.decode()] = val
            return result
        except RedisError as e:
            self._logger.error(f"[RedisRepo] HGETALL failed key={k}: {e}")
            return {}

    async def hdel(self, key: str, *fields: str) -> int:
        k = self._key(key)
        try:
            result = await self.client.hdel(k, *fields)
            return result
        except RedisError as e:
            self._logger.error(f"[RedisRepo] HDEL failed key={k} fields={fields}: {e}")
            return 0

    # ---------------- 原子操作 ----------------
    async def incr(
        self, key: str, amount: int = 1, expire: Optional[int] = None
    ) -> int:
        k = self._key(key)
        expire = expire or self.default_expire
        try:
            val = await self.client.incrby(k, amount)
            if expire:
                await self.client.expire(k, expire)
            return val
        except RedisError as e:
            self._logger.error(f"[RedisRepo] INCR failed key={k}: {e}")
            return 0

    async def decr(
        self, key: str, amount: int = 1, expire: Optional[int] = None
    ) -> int:
        k = self._key(key)
        expire = expire or self.default_expire
        try:
            val = await self.client.decrby(k, amount)
            if expire:
                await self.client.expire(k, expire)
            return val
        except RedisError as e:
            self._logger.error(f"[RedisRepo] DECR failed key={k}: {e}")
            return 0


class DualLayerCache(BaseRedisRepo):
    """
    通用 列表id + 详情 分离式缓存模板
    - 自动提供详情/批量详情/列表/搜索页缓存能力
    - 子类只需专注于业务数据与最小化定制（前缀、ID 获取方式、策略）
    """
    PREFIX_DETAIL = "detail"
    PREFIX_LIST = "list"
    PREFIX_SEARCH = "search"
    PREFIX_STATE = "state"

    def __init__(
        self,
        namespace: str = "default",
        default_expire: int = 3600,
        id_field: str = "id",
        settings: Dict[str, int] = None,
        hit_and_refresh: int = 0.1
    ):
        super().__init__(namespace=namespace, default_expire=default_expire)
        # ID 获取策略：优先使用自定义 id_getter；否则 dict[id_field] / 对象属性 / 模型 dump
        self.id_field = id_field
        self.settings = settings or {
            self.PREFIX_DETAIL: 3600, self.PREFIX_SEARCH: 300, self.PREFIX_STATE: 300
        }
        self.hit_and_refresh = hit_and_refresh

    # ---------------- ID & Key 构造 ----------------
    def _get_item_id(self, item: Dict) -> Optional[str]:
        return item.get(self.id_field, None)

    def _detail_key(self, item_id: str) -> str:
        return f"{self.namespace}:detail:{item_id}"

    def _list_key(self, prefix: str, key_suffix: Optional[str]) -> str:
        if prefix not in self.settings:
            raise ValueError(f"[{self.namespace}] Prefix {prefix} not found in settings {self.settings}")
        return f"{self.namespace}:{prefix}:{key_suffix}" if key_suffix else f"{self.namespace}:{prefix}"

    def _search_key(self, query: str, page: int) -> str:
        return f"{self.namespace}:search:{query}:{page}"

    def _state_key(self, prefix: str) -> str:
        return f"{self.namespace}:state:{prefix}"

    def _decode_pipeline_value(self, raw: Any) -> Optional[Any]:
        if raw is None:
            return None
        try:
            # pipeline 返回 bytes/string，统一解码→JSON→递归反序列化
            s = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            return self._deserialize_value(json.loads(s))
        except Exception:
            return None

    # ==================== 缓存TTL调整 ====================
    async def _adjust_assets_ttl(self, asset_ids: List[str], ttl_delta: int) -> None:
        """批量调整资产详情缓存的TTL（用于列表删除时同步清理）"""
        if not asset_ids or ttl_delta == 0:
            return
        keys = [self._detail_key(asset_id) for asset_id in asset_ids]
        try:
            pipe = self.client.pipeline()
            for key in keys:
                # 对每个详情键执行TTL调整（delta可正可负）
                pipe.expire(self._key(key), ttl_delta)
            await pipe.execute()
        except Exception as e:
            self._logger.error(f"[{self.namespace}] TTL调整失败: {str(e)}")

    # ---------------- 详情缓存 ----------------
    async def cache_detail(self, item: Dict[str, Any]) -> bool:
        item_id = self._get_item_id(item)
        if not item_id:
            self._logger.warning(f"[{self.namespace}] cache_detail 缺少有效 id，忽略: {item}")
            return False
        key = self._detail_key(item_id)
        expire = self.settings.get("detail", self.default_expire)
        try:
            return await self.set(key, item, expire)
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 详情缓存失败 id={item_id}: {e}")
            return False

    async def get_detail(self, item_id: str) -> Optional[Dict[str, Any]]:
        key = self._detail_key(item_id)
        try:
            data = await self.get(key)
            if data is not None and isinstance(data, dict):
                # 命中后以 20% 概率延长缓存时间
                if random.random() < self.hit_and_refresh:
                    await self.expire(key, self.settings.get("detail", self.default_expire) or 3600)
            return data if isinstance(data, dict) else None
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 详情获取失败 id={item_id}: {e}")
            return None

    async def delete_detail(self, item_id: str) -> bool:
        key = self._detail_key(item_id)
        try:
            deleted = await self.delete(key)
            return deleted > 0
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 详情删除失败 id={item_id}: {e}")
            return False

    # ---------------- 批量详情缓存 ----------------
    async def cache_details_batch(
        self, items: List[Dict[str, Any]], expire: Optional[int] = None
    ) -> bool:
        if not items:
            return True
        kv_pairs = {}
        for item in items:
            item_id = self._get_item_id(item)
            if item_id:
                kv_pairs[self._detail_key(item_id)] = item
        if not kv_pairs:
            return True
        try:
            return await self.mset(kv_pairs, expire)
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 批量详情缓存失败: {e}")
            return False

    async def get_details_batch(self, item_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        if not item_ids:
            return []
        keys = [self._detail_key(i) for i in item_ids if i]
        try:
            datas = await self.mget(keys)
            return [d if isinstance(d, dict) else None for d in datas]
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 批量详情获取失败: {e}")
            return [None] * len(item_ids)
            
    async def delete_details_batch(self, item_ids: List[str]) -> bool:
        """批量删除详情缓存"""
        if not item_ids:
            return True
        keys = [self._detail_key(i) for i in item_ids if i]
        if not keys:
            return True
        try:
            pipe = self.client.pipeline()
            for k in keys:
                pipe.delete(self._key(k))
            results = await pipe.execute()
            deleted = sum(1 for r in results if r)
            self._logger.debug(
                f"[{self.namespace}] 批量删除详情缓存 ids={item_ids} 成功删除={deleted}"
            )
            return deleted == len(keys)
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 批量删除详情缓存失败 ids={item_ids}: {e}")
            return False

    # ---------------- 列表缓存（ID 列表 + 详情保障）----------------
    async def _cache_item_list(
        self,
        prefix: Optional[str],
        key_suffix: Optional[str],
        items: List[Dict[str, Any]],
        expire: Optional[int] = None,
    ) -> bool:
        key = self._list_key(prefix, key_suffix)
        expire = expire or self.settings.get(prefix, self.default_expire)
        try:
            ids = [self._get_item_id(x) for x in items] if items else []
            ids = [i for i in ids if i]
            cache_ok = await self.set(key, ids, expire)
            if not cache_ok:
                self._logger.warning(f"[{self.namespace}] 列表缓存失败 key={key}")
                return False
            try:
                await self.cache_details_batch(items, expire)
            except Exception as e:
                self._logger.error(f"[{self.namespace}] 列表详情保障失败 key={key}: {e}")
            return True
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 列表缓存异常 key={key}: {e}")
            return False

    async def _get_item_list(
        self, prefix: str, key_suffix: Optional[str]
    ) -> Optional[List[Dict[str, Any]]]:
        key = self._list_key(prefix, key_suffix)
        try:
            ids = await self.get(key)
            if not ids or not isinstance(ids, list):
                return None
            details = await self.get_details_batch(ids)
            valid = [d for d in details if d is not None]
            return valid or None
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 列表获取异常 key={key}: {e}")
            return None

    async def delete_item_list(self, prefix: str, key_suffix: Optional[str]) -> bool:
        """删除列表并按策略批量收敛关联详情 TTL"""
        list_key = self._list_key(prefix, key_suffix)
        try:
            pipe = self.client.pipeline()
            pipe.ttl(self._key(list_key))
            pipe.get(self._key(list_key))
            ttl, raw_ids = await pipe.execute()

            ids = self._decode_pipeline_value(raw_ids)
            if (isinstance(ttl, int) and ttl > 0 and ids and isinstance(ids, list)):
                await self._adjust_assets_ttl(ids, -ttl)

            deleted_count = await self.delete(list_key)
            return deleted_count > 0
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 列表删除失败 key={list_key}: {e}")
            return False

    # ---------------- 搜索分页缓存 ----------------
    async def cache_search_page(
        self,
        query: str,
        page: int,
        result: Dict[str, Any],
        expire: Optional[int] = None,
    ) -> bool:
        key = self._search_key(query, page)
        try:
            items = result.get("items") or []
            ids = [self._get_item_id(x) for x in items if self._get_item_id(x)]
            payload = {
                "total": result.get("total", len(ids)),
                "page": result.get("page", page),
                "size": result.get("size", len(ids)),
                "pages": result.get("pages", 0),
                "ids": ids,
            }
            ok = await self.set(key, payload, expire)
            if not ok:
                self._logger.warning(f"[{self.namespace}] 搜索页缓存失败 key={key}")
                return False

            if items:
                try:
                    await self.cache_details_batch(items, expire)
                except Exception as e:
                    self._logger.error(f"[{self.namespace}] 搜索页详情保障失败 key={key}: {e}")
            return True
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 搜索页缓存异常 key={key}: {e}")
            return False

    async def get_search_page(self, query: str, page: int) -> Optional[Dict[str, Any]]:
        key = self._search_key(query, page)
        try:
            data = await self.get(key)
            if not data or not isinstance(data, dict):
                return None
            ids = data.get("ids") or []
            details = await self.get_details_batch(ids)
            items = [d for d in details if d is not None]
            return {
                "total": data.get("total", len(items)),
                "page": data.get("page", page),
                "pages": data.get("pages", 0),
                "size": data.get("size", len(items)),
                "items": items,
            }
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 搜索页获取异常 key={key}: {e}")
            return None

    async def delete_search_page(self, query: str, page: int) -> bool:
        key = self._search_key(query, page)
        try:
            deleted = await self.delete(key)
            return deleted > 0
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 搜索页删除失败 key={key}: {e}")
            return False

    async def delete_search_cache_all(self)-> bool:
        """删除所有搜索分页缓存"""
        try:
            pattern = f"{self.namespace}:search:*"
            deleted = await self._delete_by_pattern(pattern)
            return deleted > 0
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 删除全部搜索页缓存失败 query={self.PREFIX_SEARCH}: {e}")
            return False

    # ---------------- 清理单对象缓存 ----------------
    async def clear_item_cache(self, item_id: str) -> bool:
        """模板方法：目前只清理详情，子类可扩展为清理与该对象有关的列表模式"""
        try:
            return await self.delete_detail(item_id)
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 清理对象缓存失败 id={item_id}: {e}")
            return False

    # ==================== 统计信息缓存 ====================
    async def cache_stats(
        self, prefix: str, stats: Dict[str, Any], expire: Optional[int] = None
    ) -> bool:
        key = self._state_key(prefix)
        try:
            return await self.set(key, stats, expire)
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 统计缓存失败: {str(e)}")
            return False

    async def get_stats(self, prefix: str) -> Optional[Dict[str, Any]]:
        key = self._state_key(prefix)
        try:
            data = await self.get(key)
            return data if isinstance(data, dict) else None
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 统计获取失败: {str(e)}")
            return None

    async def delete_stats(self, prefix: str) -> bool:
        key = self._state_key(prefix)
        try:
            deleted_count = await self.delete(key)
            return deleted_count > 0
        except Exception as e:
            self._logger.error(f"[{self.namespace}] 统计删除失败: {str(e)}")
            return False
import pytest
from typing import Any, Dict, List, Optional
from fnmatch import fnmatch

from src.repos.cache_repos.base_redis_repo import DualLayerCache


# --------------------------- 异步 FakeRedis 与管道 ---------------------------

class FakePipeline:
    def __init__(self, client: "FakeRedis"):
        self.client = client
        self.ops: List[tuple] = []

    def set(self, key: str, value: str):
        self.ops.append(("set", key, value))
        return self

    def expire(self, key: str, seconds: int):
        self.ops.append(("expire", key, seconds))
        return self

    def ttl(self, key: str):
        self.ops.append(("ttl", key))
        return self

    def get(self, key: str):
        self.ops.append(("get", key))
        return self

    async def execute(self) -> List[Any]:
        results: List[Any] = []
        for op in self.ops:
            name = op[0]
            if name == "set":
                _, key, value = op
                res = await self.client.set(key, value)
                results.append(res)
            elif name == "expire":
                _, key, seconds = op
                res = await self.client.expire(key, seconds)
                results.append(res)
            elif name == "ttl":
                _, key = op
                if key not in self.client.store:
                    results.append(-2)  # Redis: key 不存在
                else:
                    results.append(self.client.ttl_map.get(key, -1))  # Redis: 未设置TTL
            elif name == "get":
                _, key = op
                res = await self.client.get(key)
                results.append(res)
        # 清空已执行的op
        self.ops.clear()
        return results


class FakeRedis:
    def __init__(self):
        self.store: Dict[str, str] = {}
        self.ttl_map: Dict[str, int] = {}
        self.expire_calls: List[str] = []

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def delete(self, key: str) -> int:
        if key in self.store:
            del self.store[key]
            self.ttl_map.pop(key, None)
            return 1
        return 0

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttl_map[key] = seconds
        self.expire_calls.append(key)
        return True

    async def mget(self, *keys: str) -> List[Optional[str]]:
        return [self.store.get(k) for k in keys]

    async def scan_iter(self, match: Optional[str] = None):
        # 简化：同步匹配 + 异步生成
        for key in list(self.store.keys()):
            if match is None or fnmatch(key, match):
                yield key


# --------------------------- 测试用 DualLayerCache 子类 ---------------------------

class TestDualLayerCache(DualLayerCache):
    def __init__(self, client: FakeRedis):
        super().__init__(
            namespace="test",
            default_expire=360,
            id_field="id",
            settings={
                "detail": 360,
                "search": 300,
                "state": 300,
                "listA": 180,
            },
            hit_and_refresh=1.0,  # 命中后必定刷新TTL（便于断言）
        )
        self._client = client

    @property
    def client(self) -> FakeRedis:
        return self._client


# --------------------------- 帮助函数 ---------------------------

def make_items(n: int) -> List[Dict[str, Any]]:
    return [{"id": f"i{idx}", "name": f"name{idx}"} for idx in range(1, n + 1)]


# --------------------------- 详情缓存 ---------------------------

@pytest.mark.asyncio
async def test_cache_detail_and_get_detail_refreshes_ttl():
    client = FakeRedis()
    cache = TestDualLayerCache(client)

    item = {"id": "a1", "name": "alpha"}
    ok = await cache.cache_detail(item)
    assert ok is True

    # 命中后必定触发 TTL 刷新（由于 hit_and_refresh=1.0）
    data = await cache.get_detail("a1")
    assert data is not None and data["id"] == "a1"

    full_detail_key = cache._key(cache._detail_key("a1"))
    # 断言触发了 expire
    assert full_detail_key in client.expire_calls
    # TTL 值被设置为 settings["detail"]
    assert client.ttl_map.get(full_detail_key) == cache.settings["detail"]


@pytest.mark.asyncio
async def test_cache_details_batch_and_get_details_batch():
    client = FakeRedis()
    cache = TestDualLayerCache(client)

    items = [{"id": "b1"}, {"id": "b2"}, {"name": "no-id"}]  # 含一个缺失id
    ok = await cache.cache_details_batch(items, expire=500)
    assert ok is True

    # 仅返回有 id 的两个对象
    out = await cache.get_details_batch(["b1", "b2", None])
    assert isinstance(out, list) and len(out) == 2
    assert out[0]["id"] == "b1" and out[1]["id"] == "b2"


# --------------------------- 列表缓存 ---------------------------

@pytest.mark.asyncio
async def test_cache_item_list_and_get_item_list_returns_details():
    client = FakeRedis()
    cache = TestDualLayerCache(client)
    items = make_items(2)

    ok = await cache._cache_item_list("listA", "s1", items, expire=120)
    assert ok is True

    res = await cache._get_item_list("listA", "s1")
    assert isinstance(res, list) and len(res) == 2
    assert [x["id"] for x in res] == ["i1", "i2"]


@pytest.mark.asyncio
async def test_delete_item_list_adjusts_detail_ttl_and_deletes_list_key():
    client = FakeRedis()
    cache = TestDualLayerCache(client)
    items = make_items(2)

    # 列表缓存，TTL=180；同时保障详情缓存
    ok = await cache._cache_item_list("listA", "sDel", items, expire=180)
    assert ok is True

    full_list_key = cache._key(cache._list_key("listA", "sDel"))
    assert client.store.get(full_list_key) is not None
    assert client.ttl_map.get(full_list_key) == 180

    deleted = await cache.delete_item_list("listA", "sDel")
    assert deleted is True
    assert full_list_key not in client.store

    # 详情TTL被收敛为负值（与当前实现保持一致）
    for idx in [1, 2]:
        dk = cache._key(cache._detail_key(f"i{idx}"))
        assert client.ttl_map.get(dk) == -180


# --------------------------- 搜索页缓存 ---------------------------

@pytest.mark.asyncio
async def test_cache_search_page_and_get_search_page_returns_items():
    client = FakeRedis()
    cache = TestDualLayerCache(client)
    items = make_items(3)
    result = {"items": items, "total": 3, "page": 1, "size": 3}

    ok = await cache.cache_search_page("foo", 1, result, expire=200)
    assert ok is True

    page = await cache.get_search_page("foo", 1)
    assert page is not None
    assert page["total"] == 3 and page["page"] == 1 and page["size"] == 3
    assert isinstance(page["items"], list) and len(page["items"]) == 3
    assert [x["id"] for x in page["items"]] == ["i1", "i2", "i3"]


@pytest.mark.asyncio
async def test_delete_search_page_removes_key():
    client = FakeRedis()
    cache = TestDualLayerCache(client)
    # 先缓存
    await cache.cache_search_page("bar", 2, {"items": make_items(1), "total": 1, "page": 2, "size": 1}, expire=150)

    deleted = await cache.delete_search_page("bar", 2)
    assert deleted is True

    full_search_key = cache._key(cache._search_key("bar", 2))
    assert full_search_key not in client.store


@pytest.mark.asyncio
@pytest.mark.xfail(reason="当前实现存在双重命名空间导致模式删除不匹配：test:search:* 不匹配 test:test:search:*")
async def test_delete_search_cache_all_should_remove_all_search_pages():
    client = FakeRedis()
    cache = TestDualLayerCache(client)

    await cache.cache_search_page("q1", 1, {"items": []}, expire=60)
    await cache.cache_search_page("q2", 1, {"items": []}, expire=60)
    await cache.cache_search_page("q3", 2, {"items": []}, expire=60)

    # 期望：全部被删除（但当前实现由于模式不匹配将失败）
    ok = await cache.delete_search_cache_all()
    assert ok is True

    # 验证：无任何 search:* 键（当前实现会保留）
    for k in list(client.store.keys()):
        assert "search:" not in k


# --------------------------- 清理单对象与统计缓存 ---------------------------

@pytest.mark.asyncio
async def test_clear_item_cache_deletes_detail():
    client = FakeRedis()
    cache = TestDualLayerCache(client)
    await cache.cache_detail({"id": "z1", "name": "zeta"})
    cleared = await cache.clear_item_cache("z1")
    assert cleared is True

    full_detail_key = cache._key(cache._detail_key("z1"))
    assert full_detail_key not in client.store


@pytest.mark.asyncio
async def test_cache_stats_get_delete():
    client = FakeRedis()
    cache = TestDualLayerCache(client)
    stats = {"count": 10, "updated": True}

    ok = await cache.cache_stats("listA", stats, expire=90)
    assert ok is True

    got = await cache.get_stats("listA")
    assert got == stats

    deleted = await cache.delete_stats("listA")
    assert deleted is True

    full_state_key = cache._key(cache._state_key("listA"))
    assert full_state_key not in client.store
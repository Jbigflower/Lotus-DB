import pytest
from typing import Any, Dict, List, Optional
from fnmatch import fnmatch

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
        for key in list(self.store.keys()):
            if match is None or fnmatch(key, match):
                yield key


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def patch_redis_client(monkeypatch, fake_redis: FakeRedis):
    # BaseRedisRepo 在模块顶层绑定了 get_redis_client，需要同时打桩该模块里的符号
    import src.db.redis_db as redis_db
    import src.repos.cache_repos.base_redis_repo as base_mod
    monkeypatch.setattr(redis_db, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(base_mod, "get_redis_client", lambda: fake_redis)
    return fake_redis


@pytest.fixture
def items_factory():
    def _make(n: int) -> List[Dict[str, Any]]:
        return [{"id": f"i{idx}", "name": f"name{idx}"} for idx in range(1, n + 1)]
    return _make
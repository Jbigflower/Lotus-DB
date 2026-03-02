import os
import sys
import pytest
import tempfile
import asyncio
from typing import Any, Dict, List, Optional
from fnmatch import fnmatch
from bson import ObjectId
from unittest.mock import MagicMock

# Add project root to sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config.setting import settings
from src.db.mongo_db import init_mongo, close_mongo, MongoManager

# --------------------------- Helper Functions ---------------------------

def pytest_addoption(parser):
    parser.addoption("--llm_judge", action="store_true", default=False)
    parser.addoption("--agent_arch", action="store", default="react")

@pytest.fixture(scope="session")
def llm_judge_enabled(request):
    return request.config.getoption("llm_judge")

@pytest.fixture(scope="session")
def agent_arch(request):
    return request.config.getoption("agent_arch")

def get_random_object_id() -> str:
    return str(ObjectId())

# --------------------------- Test Environment Setup ---------------------------

@pytest.fixture(scope="session")
def test_env_settings():
    """
    Override Settings
    """
    with tempfile.TemporaryDirectory() as temp_lancedb_dir:
        original_lancedb_path = settings.database.lancedb_path
        
        settings.database.lancedb_path = temp_lancedb_dir
        
        yield settings
        
        settings.database.lancedb_path = original_lancedb_path

@pytest.fixture(scope="session")
async def mongo_connection(test_env_settings):
    """
    Initialize MongoDB Connection for the session using mongomock
    """
    from mongomock_motor import AsyncMongoMockClient
    
    # Patch MongoManager.connect to use AsyncMongoMockClient
    original_connect = MongoManager.connect
    
    async def mock_connect(self):
        if self._is_connected:
            return
        self._client = AsyncMongoMockClient()
        self._db = self._client[self._settings.mongo_db]
        self._is_connected = True
        # Mock create_indexes to do nothing or pass
        try:
             await self._create_indexes()
        except Exception:
             pass 

    MongoManager.connect = mock_connect
    
    await init_mongo()
    yield
    await close_mongo()
    
    # Restore original connect
    MongoManager.connect = original_connect

# --------------------------- Fake Redis Implementation ---------------------------

class FakePipeline:
    def __init__(self, client: "FakeRedis"):
        self.client = client
        self.ops: List[tuple] = []

    def set(self, key: str, value: str, ex: int = None):
        self.ops.append(("set", key, value, ex))
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
        
    def delete(self, key: str):
        self.ops.append(("delete", key))
        return self

    async def execute(self) -> List[Any]:
        results: List[Any] = []
        for op in self.ops:
            name = op[0]
            if name == "set":
                _, key, value, ex = op
                res = await self.client.set(key, value, ex=ex)
                results.append(res)
            elif name == "expire":
                _, key, seconds = op
                res = await self.client.expire(key, seconds)
                results.append(res)
            elif name == "ttl":
                _, key = op
                res = await self.client.ttl(key)
                results.append(res)
            elif name == "get":
                _, key = op
                res = await self.client.get(key)
                results.append(res)
            elif name == "delete":
                _, key = op
                res = await self.client.delete(key)
                results.append(res)
        return results

class FakeRedis:
    def __init__(self):
        self.data: Dict[str, str] = {}
        self.ttls: Dict[str, int] = {}
        self.hash_data: Dict[str, Dict[str, str]] = {}

    async def get(self, key: str) -> Optional[str]:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int = None) -> bool:
        self.data[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    async def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            if key in self.ttls:
                del self.ttls[key]
            return 1
        if key in self.hash_data:
            del self.hash_data[key]
            return 1
        return 0

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self.data or key in self.hash_data:
            self.ttls[key] = seconds
            return True
        return False

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    def pipeline(self):
        return FakePipeline(self)
    
    async def hget(self, name: str, key: str) -> Optional[str]:
        return self.hash_data.get(name, {}).get(key)
    
    async def hset(self, name: str, key: str, value: str) -> int:
        if name not in self.hash_data:
            self.hash_data[name] = {}
        self.hash_data[name][key] = value
        return 1
    
    async def hgetall(self, name: str) -> Dict[str, str]:
        return self.hash_data.get(name, {})
        
    async def scan_iter(self, match: str = None, count: int = None):
        import fnmatch
        for key in self.data:
            if match and not fnmatch.fnmatch(key, match):
                continue
            yield key

@pytest.fixture(autouse=True)
async def override_get_redis_client(monkeypatch):
    fake_redis = FakeRedis()
    
    # Patch the get_redis_client in src.db.redis_db
    import src.db.redis_db
    monkeypatch.setattr(src.db.redis_db, "get_redis_client", lambda: fake_redis)
    
    return fake_redis


# --------------------------- Data Seeding Fixture ---------------------------

@pytest.fixture(scope="session")
async def test_seeder(mongo_connection):
    """
    Initialize and seed test data (Lotus World)
    Session scope, runs once.
    """
    from tests.seed_data import DataSeeder
    
    seeder = DataSeeder()
    await seeder.seed_all()
    return seeder

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

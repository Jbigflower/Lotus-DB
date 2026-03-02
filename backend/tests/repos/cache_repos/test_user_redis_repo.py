import pytest

from src.repos.cache_repos.user_redis_repo import UserRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client


@pytest.mark.asyncio
async def test_namespace_and_default_expire(patch_redis_client):
    repo = UserRedisRepo()
    assert repo.namespace == "user"
    assert repo.default_expire == 86400


@pytest.mark.asyncio
async def test_jwt_cache_get_and_revoke(patch_redis_client):
    repo = UserRedisRepo()
    user_id = "u1"

    ok = await repo.cache_user_jwt(user_id, "tok123", expire=60)
    assert ok is True

    got = await repo.get_user_jwt(user_id)
    assert got == "tok123"

    jwt_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:jwt")
    assert patch_redis_client.ttl_map.get(jwt_key) == 60

    revoked = await repo.revoke_user_jwt(user_id)
    assert revoked is True
    assert await repo.get_user_jwt(user_id) is None


@pytest.mark.asyncio
async def test_user_info_cache_get(patch_redis_client):
    repo = UserRedisRepo()
    user_id = "u2"
    info = {"name": "Lotus", "email": "lotus@example.com", "roles": ["admin"]}

    ok = await repo.cache_user_info(user_id, info, expire=120)
    assert ok is True

    data = await repo.get_user_info(user_id)
    assert data and data["id"] == user_id and data["name"] == "Lotus"

    info_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:info")
    assert patch_redis_client.ttl_map.get(info_key) == 120


@pytest.mark.asyncio
async def test_cache_user_session_and_get(patch_redis_client):
    repo = UserRedisRepo()
    user_id = "u3"

    ok = await repo.cache_user_session(user_id, "token-xyz", {"nick": "L"}, expire=180)
    assert ok is True

    sess = await repo.get_user_session(user_id)
    assert sess and sess["jwt"] == "token-xyz" and sess["user"]["id"] == user_id

    jwt_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:jwt")
    info_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:info")
    assert patch_redis_client.ttl_map.get(jwt_key) == 180
    assert patch_redis_client.ttl_map.get(info_key) == 180


@pytest.mark.asyncio
async def test_get_user_session_partial_and_none(patch_redis_client):
    repo = UserRedisRepo()
    # 未缓存时返回 None
    assert await repo.get_user_session("none") is None

    # 仅缓存 JWT 时返回包含 jwt，user 为 None
    user_id = "u4"
    assert await repo.cache_user_jwt(user_id, "only-jwt", expire=60) is True
    sess = await repo.get_user_session(user_id)
    assert sess and sess["jwt"] == "only-jwt" and sess["user"] is None


@pytest.mark.asyncio
async def test_refresh_and_exists_session(patch_redis_client):
    repo = UserRedisRepo()
    user_id = "u5"
    await repo.cache_user_session(user_id, "tok", {"name": "N"}, expire=100)

    assert await repo.exists_session(user_id) is True

    # 刷新 TTL
    ok = await repo.refresh_session_ttl(user_id, seconds=900)
    assert ok is True

    jwt_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:jwt")
    info_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:info")
    assert patch_redis_client.ttl_map.get(jwt_key) == 900
    assert patch_redis_client.ttl_map.get(info_key) == 900

    # 清理后不存在
    assert await repo.clear_user_cache(user_id) is True
    assert await repo.exists_session(user_id) is False


@pytest.mark.asyncio
async def test_clear_user_cache_removes_all_keys(patch_redis_client):
    repo = UserRedisRepo()
    user_id = "u6"

    await repo.cache_user_jwt(user_id, "tok", expire=50)
    await repo.cache_user_info(user_id, {"age": 18}, expire=50)
    # 设置 prefs 原始键（在 BaseRedisRepo 中会再加命名空间）
    assert await repo.set(f"prefs:{user_id}", {"theme": "dark"}, expire=300) is True

    assert await repo.clear_user_cache(user_id) is True

    jwt_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:jwt")
    info_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:info")
    prefs_key = repo._key(f"prefs:{user_id}")
    # FakeRedis.delete 会清除 store 与 ttl_map
    assert jwt_key not in patch_redis_client.store
    assert info_key not in patch_redis_client.store
    assert prefs_key not in patch_redis_client.store


@pytest.mark.asyncio
async def test_current_library_set_get_delete(patch_redis_client):
    repo = UserRedisRepo()
    user_id = "u7"
    lib = {"id": "lib1", "name": "Main"}

    assert await repo.set_current_library(user_id, lib, expire=600) is True

    got = await repo.get_current_library(user_id)
    assert got and got["id"] == "lib1"

    lib_key = repo._key(f"{repo.PREFIX_USER}:{user_id}:current_library")
    assert patch_redis_client.ttl_map.get(lib_key) == 600

    assert await repo.delete_current_library(user_id) is True
    assert lib_key not in patch_redis_client.store
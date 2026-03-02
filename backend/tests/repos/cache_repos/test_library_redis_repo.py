import pytest
from src.repos.cache_repos.library_redis_repo import LibraryRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = LibraryRedisRepo()
    assert repo.namespace == "library"
    assert set(["detail", "search", "state"]).issubset(set(repo.settings.keys()))


@pytest.mark.asyncio
async def test_detail_cache_and_refresh_ttl(patch_redis_client):
    repo = LibraryRedisRepo()
    repo.hit_and_refresh = 1.0
    item = {"id": "l1", "name": "lib"}

    assert await repo.cache_detail(item) is True
    data = await repo.get_detail("l1")
    assert data and data["id"] == "l1"

    full_key = repo._key(repo._detail_key("l1"))
    assert full_key in patch_redis_client.expire_calls
    assert patch_redis_client.ttl_map.get(full_key) == repo.settings["detail"]


@pytest.mark.asyncio
async def test_search_page_cache_get_and_delete(patch_redis_client):
    repo = LibraryRedisRepo()
    ok = await repo.cache_search_page("libq", 1, {"items": [{"id": "l1"}], "total": 1, "page": 1, "size": 1}, expire=100)
    assert ok is True

    page = await repo.get_search_page("libq", 1)
    assert page and page["items"][0]["id"] == "l1"

    deleted = await repo.delete_search_page("libq", 1)
    assert deleted is True


@pytest.mark.asyncio
async def test_stats_cache_get_delete(patch_redis_client):
    repo = LibraryRedisRepo()
    stats = {"count": 5}
    assert await repo.cache_stats("state", stats, expire=50) is True
    assert await repo.get_stats("state") == stats
    assert await repo.delete_stats("state") is True
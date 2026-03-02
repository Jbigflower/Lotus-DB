import pytest
from src.repos.cache_repos.user_custom_list_redis_repo import UserCustomListRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = UserCustomListRedisRepo()
    assert repo.namespace == "user_custom_lists"
    assert "user" in repo.settings


@pytest.mark.asyncio
async def test_list_cache_user_and_delete_adjusts_detail_ttl(patch_redis_client):
    repo = UserCustomListRedisRepo()
    items = [{"id": "c1"}, {"id": "c2"}]
    assert await repo._cache_item_list("user", "u42", items, expire=240) is True

    got = await repo._get_item_list("user", "u42")
    assert got and [x["id"] for x in got] == ["c1", "c2"]

    assert await repo.delete_item_list("user", "u42") is True
    for suffix in ["c1", "c2"]:
        dk = repo._key(repo._detail_key(suffix))
        assert patch_redis_client.ttl_map.get(dk) == -240


@pytest.mark.asyncio
async def test_search_page_and_delete(patch_redis_client):
    repo = UserCustomListRedisRepo()
    await repo.cache_search_page("cl", 1, {"items": [{"id": "c1"}]}, expire=100)
    page = await repo.get_search_page("cl", 1)
    assert page and page["items"][0]["id"] == "c1"
    assert await repo.delete_search_page("cl", 1) is True
import pytest
from src.repos.cache_repos.user_asset_redis_repo import UserAssetRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = UserAssetRedisRepo()
    assert repo.namespace == "user_assets"
    assert repo.PREFIX_MOVIE_USER in repo.settings


@pytest.mark.asyncio
async def test_list_cache_movie_and_delete_adjusts_detail_ttl(patch_redis_client):
    repo = UserAssetRedisRepo()
    items = [{"id": "ua1"}, {"id": "ua2"}]
    user_id, movie_id = "u1", "m1"
    assert await repo._cache_movie_list(movie_id, user_id, items, expire=200) is True

    got = await repo._get_movie_list(movie_id, user_id)
    assert got and [x["id"] for x in got] == ["ua1", "ua2"]

    assert await repo.delete_movie_list(movie_id, user_id) is True
    for suffix in ["ua1", "ua2"]:
        dk = repo._key(repo._detail_key(suffix))
        assert patch_redis_client.ttl_map.get(dk) == -200


@pytest.mark.asyncio
async def test_search_page_and_delete(patch_redis_client):
    repo = UserAssetRedisRepo()
    await repo.cache_search_page("tag", 1, {"items": [{"id": "ua1"}]}, expire=100)
    page = await repo.get_search_page("tag", 1)
    assert page and page["items"][0]["id"] == "ua1"
    assert await repo.delete_search_page("tag", 1) is True
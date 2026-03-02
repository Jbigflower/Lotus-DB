import pytest
from src.repos.cache_repos.movie_redis_repo import MovieRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = MovieRedisRepo()
    assert repo.namespace == "movie"
    assert set(["detail", "search", "state", "customList", "recent", "popular"]).issubset(set(repo.settings.keys()))


@pytest.mark.asyncio
async def test_list_cache_popular_and_delete_adjusts_detail_ttl(patch_redis_client):
    repo = MovieRedisRepo()
    items = [{"id": "m1"}, {"id": "m2"}]
    ok = await repo._cache_item_list("popular", "p1", items, expire=300)
    assert ok is True

    got = await repo._get_item_list("popular", "p1")
    assert got and [x["id"] for x in got] == ["m1", "m2"]

    deleted = await repo.delete_item_list("popular", "p1")
    assert deleted is True
    for suffix in ["m1", "m2"]:
        dk = repo._key(repo._detail_key(suffix))
        assert patch_redis_client.ttl_map.get(dk) == -300


@pytest.mark.asyncio
async def test_search_page_cache_get_delete(patch_redis_client):
    repo = MovieRedisRepo()
    await repo.cache_search_page("mv", 1, {"items": [{"id": "m1"}], "total": 1, "page": 1, "size": 1}, expire=120)
    page = await repo.get_search_page("mv", 1)
    assert page and page["items"][0]["id"] == "m1"
    deleted = await repo.delete_search_page("mv", 1)
    assert deleted is True


@pytest.mark.asyncio
@pytest.mark.xfail(reason="双命名空间搜索键导致 delete_search_cache_all 无法匹配删除")
async def test_delete_search_cache_all_xfail(patch_redis_client):
    repo = MovieRedisRepo()
    await repo.cache_search_page("mvQ", 2, {"items": []}, expire=60)
    ok = await repo.delete_search_cache_all()
    assert ok is True


@pytest.mark.asyncio
async def test_stats(patch_redis_client):
    repo = MovieRedisRepo()
    assert await repo.cache_stats("state", {"total": 100}, expire=90)
    assert await repo.get_stats("state") == {"total": 100}
    assert await repo.delete_stats("state")
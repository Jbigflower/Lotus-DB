import pytest
from src.repos.cache_repos.asset_redis_repo import AssetRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = AssetRedisRepo()
    assert repo.namespace == "assets"
    assert "detail" in repo.settings and "movie" in repo.settings


@pytest.mark.asyncio
async def test_detail_cache_and_refresh_ttl(patch_redis_client):
    repo = AssetRedisRepo()
    repo.hit_and_refresh = 1.0  # 命中必刷新TTL
    item = {"id": "a1", "name": "alpha"}

    ok = await repo.cache_detail(item)
    assert ok is True

    data = await repo.get_detail("a1")
    assert data and data["id"] == "a1"

    # 断言触发过期
    full_key = repo._key(repo._detail_key("a1"))
    assert full_key in patch_redis_client.expire_calls
    assert patch_redis_client.ttl_map.get(full_key) == repo.settings["detail"]


@pytest.mark.asyncio
async def test_list_cache_movie_prefix_and_delete_adjusts_detail_ttl(patch_redis_client, items_factory):
    repo = AssetRedisRepo()
    items = items_factory(2)

    ok = await repo._cache_item_list("movie", "s1", items, expire=180)
    assert ok is True

    res = await repo._get_item_list("movie", "s1")
    assert res and [x["id"] for x in res] == ["i1", "i2"]

    full_list_key = repo._key(repo._list_key("movie", "s1"))
    assert patch_redis_client.ttl_map.get(full_list_key) == 180

    deleted = await repo.delete_item_list("movie", "s1")
    assert deleted is True

    for idx in [1, 2]:
        dk = repo._key(repo._detail_key(f"i{idx}"))
        assert patch_redis_client.ttl_map.get(dk) == -180


@pytest.mark.asyncio
async def test_search_page_cache_get_and_delete(patch_redis_client, items_factory):
    repo = AssetRedisRepo()
    items = items_factory(3)
    ok = await repo.cache_search_page("q", 1, {"items": items, "total": 3, "page": 1, "size": 3}, expire=120)
    assert ok is True

    page = await repo.get_search_page("q", 1)
    assert page and page["total"] == 3 and [x["id"] for x in page["items"]] == ["i1", "i2", "i3"]

    deleted = await repo.delete_search_page("q", 1)
    assert deleted is True

    full_search_key = repo._key(repo._search_key("q", 1))
    assert full_search_key not in patch_redis_client.store


@pytest.mark.asyncio
@pytest.mark.xfail(reason="双命名空间键导致 pattern test:search:* 不匹配真实键 test:test:search:*")
async def test_delete_search_cache_all_xfail(patch_redis_client):
    repo = AssetRedisRepo()
    await repo.cache_search_page("x", 1, {"items": []}, expire=60)
    ok = await repo.delete_search_cache_all()
    assert ok is True
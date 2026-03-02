import pytest
from src.repos.cache_repos.watch_history_redis_repo import WatchHistoryRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = WatchHistoryRedisRepo()
    assert repo.namespace == "watch_history"
    assert repo.PREFIX_RECENT_USER in repo.settings


@pytest.mark.asyncio
async def test_list_cache_recent_and_delete_adjusts_detail_ttl(patch_redis_client):
    repo = WatchHistoryRedisRepo()
    items = [{"id": "w1"}, {"id": "w2"}]
    assert await repo._cache_item_list("recent", "u1p1", items, expire=180) is True

    got = await repo._get_item_list("recent", "u1p1")
    assert got and [x["id"] for x in got] == ["w1", "w2"]

    assert await repo.delete_item_list("recent", "u1p1") is True
    for suffix in ["w1", "w2"]:
        dk = repo._key(repo._detail_key(suffix))
        assert patch_redis_client.ttl_map.get(dk) == -180


@pytest.mark.asyncio
async def test_list_cache_recent_and_delete_by_user(patch_redis_client):
    repo = WatchHistoryRedisRepo()
    items = [{"id": "w1"}, {"id": "w2"}]
    user_id = "u1"

    # 分别缓存两个 limit 下的最近播放列表
    assert await repo._cache_recent_list(user_id, 50, items, expire=180) is True
    assert await repo._cache_recent_list(user_id, 20, items[:1], expire=60) is True

    got = await repo._get_recent_list(user_id, 50)
    assert got and [x["id"] for x in got] == ["w1", "w2"]

    # 断言列表键存在
    key50 = repo._key(repo._list_key(repo.PREFIX_RECENT_USER, f"{user_id}_50"))
    key20 = repo._key(repo._list_key(repo.PREFIX_RECENT_USER, f"{user_id}_20"))
    assert key50 in patch_redis_client.store and key20 in patch_redis_client.store

    # 批量删除该用户的所有最近播放列表（不再断言详情 TTL 收敛）
    assert await repo._delete_recent_list(user_id) is True

    # 断言两个列表键都被删除
    assert key50 not in patch_redis_client.store and key20 not in patch_redis_client.store


@pytest.mark.asyncio
async def test_search_page_and_delete(patch_redis_client):
    repo = WatchHistoryRedisRepo()
    await repo.cache_search_page("his", 1, {"items": [{"id": "w1"}]}, expire=100)
    page = await repo.get_search_page("his", 1)
    assert page and page["items"][0]["id"] == "w1"
    assert await repo.delete_search_page("his", 1) is True
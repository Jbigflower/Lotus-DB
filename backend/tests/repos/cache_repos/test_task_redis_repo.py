import pytest
from src.repos.cache_repos.task_redis_repo import TaskRedisRepo
from tests.repos.cache_repos.conftest import patch_redis_client

@pytest.mark.asyncio
async def test_namespace_and_settings(patch_redis_client):
    repo = TaskRedisRepo()
    assert repo.namespace == "task"
    assert set(["detail", "search", "state"]).issubset(set(repo.settings.keys()))


@pytest.mark.asyncio
async def test_detail_and_search_page(patch_redis_client):
    repo = TaskRedisRepo()
    repo.hit_and_refresh = 1.0
    assert await repo.cache_detail({"id": "t1", "status": "running"}) is True
    assert (await repo.get_detail("t1"))["id"] == "t1"

    await repo.cache_search_page("job", 1, {"items": [{"id": "t1"}], "total": 1, "page": 1, "size": 1}, expire=50)
    page = await repo.get_search_page("job", 1)
    assert page and page["items"][0]["id"] == "t1"

    assert await repo.delete_search_page("job", 1) is True


@pytest.mark.asyncio
async def test_stats(patch_redis_client):
    repo = TaskRedisRepo()
    assert await repo.cache_stats("state", {"running": 3}, expire=60)
    assert await repo.get_stats("state") == {"running": 3}
    assert await repo.delete_stats("state")
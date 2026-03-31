import pytest

from src.agent.tools import movie_tools
from src.agent.tools.movie_tools import register_movie_tools
from src.agent.tools.registry import ToolRegistry
from src.agent.types import RequestContext


class FakeUser:
    def __init__(self) -> None:
        self.id = "u1"
        self.role = "admin"


class FakeMoviePage:
    def model_dump_json(self) -> str:
        return '{"items": [], "total": 0}'


@pytest.mark.asyncio
async def test_movie_list_tool_executes(monkeypatch) -> None:
    class FakeService:
        async def list_movies(self, **kwargs):
            return FakeMoviePage()

    async def fake_get_current_user(ctx: RequestContext):
        return FakeUser()

    monkeypatch.setattr(movie_tools, "_get_current_user", fake_get_current_user)
    monkeypatch.setattr(movie_tools, "_get_movie_service", lambda: FakeService())

    registry = ToolRegistry()
    register_movie_tools(registry)
    ctx = RequestContext(user_id="u1", session_id="s1", trace_id="t1")

    result = await registry.execute("list_movies", {"page": 1, "size": 20}, ctx=ctx)

    assert "电影列表" in result.output
    assert result.error is None

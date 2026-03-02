from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import os
from config.setting import settings


class DDGSearchSchema(BaseModel):
    query: str = Field(description="搜索关键词")
    max_results: int = Field(default=10, description="返回数量")
    search_type: str = Field(default="text", description="类型 text|news|images")
    region: Optional[str] = Field(default=None, description="地区代码，如 us-en, cn-zh")
    safesearch: Optional[str] = Field(default=None, description="安全级别 off|moderate|strict")
    timelimit: Optional[str] = Field(default=None, description="时间范围，如 d|w|m|y")


class OMDBSearchSchema(BaseModel):
    title: str = Field(description="影片标题")
    year: Optional[int] = Field(default=None, description="年份")
    type: Optional[str] = Field(default=None, description="类型 movie|series|episode")
    page: int = Field(default=1, description="页码 1-100")


class OMDBGetSchema(BaseModel):
    imdb_id: str = Field(description="IMDB ID，如 tt1375666")
    plot: str = Field(default="full", description="剧情长度 short|full")


@tool(args_schema=DDGSearchSchema)
async def ddg_search_tool(
    query: str,
    max_results: int,
    search_type: str,
    region: Optional[str],
    safesearch: Optional[str],
    timelimit: Optional[str],
    runtime: ToolRuntime,
) -> str:
    """使用 DuckDuckGo 进行外部搜索，支持文本、新闻、图片。"""
    current_user = runtime.context.get("user")
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from duckduckgo_search import DDGS

        def _run():
            with DDGS() as ddgs:
                if search_type == "news":
                    gen = ddgs.news(
                        query,
                        max_results=max_results,
                        region=region,
                        safesearch=safesearch,
                        timelimit=timelimit,
                    )
                elif search_type == "images":
                    gen = ddgs.images(
                        query,
                        max_results=max_results,
                        region=region,
                        safesearch=safesearch,
                    )
                else:
                    gen = ddgs.text(
                        query,
                        max_results=max_results,
                        region=region,
                        safesearch=safesearch,
                        timelimit=timelimit,
                    )
                return list(gen)

        results = await asyncio.to_thread(_run)
        if search_type == "images":
            items = [
                {
                    "title": r.get("title"),
                    "image": r.get("image"),
                    "url": r.get("url"),
                    "thumbnail": r.get("thumbnail"),
                }
                for r in results
            ]
        elif search_type == "news":
            items = [
                {
                    "title": r.get("title"),
                    "date": r.get("date"),
                    "url": r.get("url"),
                    "source": r.get("source"),
                }
                for r in results
            ]
        else:
            items = [
                {
                    "title": r.get("title"),
                    "url": r.get("href") or r.get("url"),
                    "snippet": r.get("body") or r.get("description"),
                }
                for r in results
            ]
        return f"外部搜索结果: {{'type': '{search_type}', 'items': {items}}}"
    except Exception as e:
        return f"搜索失败: {str(e)}"


@tool(args_schema=OMDBSearchSchema)
async def omdb_search_tool(
    title: str,
    year: Optional[int],
    type: Optional[str],
    page: int,
    runtime: ToolRuntime,
) -> str:
    """从 OMDb 搜索影片概要信息。"""
    current_user = runtime.context.get("user")
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        api_key = getattr(getattr(settings, "plugins", object()), "omdb_api_key", None) or os.getenv("OMDB_API_KEY")
        if not api_key:
            return "错误：未配置 OMDB API KEY。"
        import requests

        params = {"apikey": api_key, "s": title, "page": page}
        if year is not None:
            params["y"] = str(year)
        if type:
            params["type"] = type

        def _req():
            resp = requests.get(
                "https://www.omdbapi.com/",
                params=params,
                timeout=settings.performance.external_api_timeout,
            )
            resp.raise_for_status()
            return resp.json()

        data = await asyncio.to_thread(_req)
        if data.get("Response") != "True":
            err = data.get("Error") or "Unknown"
            return f"查询失败: {err}"
        items = data.get("Search", [])
        return f"OMDb 搜索结果: {items}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=OMDBGetSchema)
async def omdb_get_tool(
    imdb_id: str,
    plot: str,
    runtime: ToolRuntime,
) -> str:
    """从 OMDb 获取影片详细信息。"""
    current_user = runtime.context.get("user")
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        api_key = getattr(getattr(settings, "plugins", object()), "omdb_api_key", None) or os.getenv("OMDB_API_KEY")
        if not api_key:
            return "错误：未配置 OMDB API KEY。"
        import requests

        params = {"apikey": api_key, "i": imdb_id, "plot": plot or "full"}

        def _req():
            resp = requests.get(
                "https://www.omdbapi.com/",
                params=params,
                timeout=settings.performance.external_api_timeout,
            )
            resp.raise_for_status()
            return resp.json()

        data = await asyncio.to_thread(_req)
        if data.get("Response") != "True":
            err = data.get("Error") or "Unknown"
            return f"获取失败: {err}"
        return f"OMDb 详情: {data}"
    except Exception as e:
        return f"获取失败: {str(e)}"


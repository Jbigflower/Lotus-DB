from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
from src.services.search.search_service import SearchService


class GlobalSearchSchema(BaseModel):
    q: str = Field(description="搜索关键词")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")
    only_me: bool = Field(default=False, description="只看我的资源")
    type: str = Field(default="summary", description="结果类型 summary|libraries|movies|user_assets|collections|movie_assets")


class NSSearchSchema(BaseModel):
    query: str = Field(description="搜索关键词")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")
    only_me: bool = Field(default=False, description="只看我的资源")
    types: Optional[List[str]] = Field(default=None, description="检索域 movies|notes|subtitles")
    top_k: Optional[int] = Field(default=None, description="召回上限")
    vector_weight: float = Field(default=0.7, description="向量分权重")
    keyword_weight: float = Field(default=0.3, description="关键词分权重")
    max_per_parent: int = Field(default=2, description="同父项最多条数")
    use_cache: bool = Field(default=False, description="是否启用缓存")


@tool(args_schema=GlobalSearchSchema)
async def global_search_tool(
    q: str,
    page: int,
    size: int,
    only_me: bool,
    type: str,
    runtime: ToolRuntime,
) -> str:
    """执行全局搜索，按类型返回聚合结果。"""
    current_user = runtime.context.get("user")
    service = SearchService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.search(
            q=q,
            page=page,
            size=size,
            only_me=only_me,
            type=type,
            current_user=current_user,
        )
        return f"全局搜索结果: {result}"
    except Exception as e:
        return f"搜索失败: {str(e)}"


@tool(args_schema=NSSearchSchema)
async def ns_search_tool(
    query: str,
    page: int,
    size: int,
    only_me: bool,
    types: Optional[List[str]],
    top_k: Optional[int],
    vector_weight: float,
    keyword_weight: float,
    max_per_parent: int,
    use_cache: bool,
    runtime: ToolRuntime,
) -> str:
    """执行向量+关键词混合检索，支持多域与权重配置。"""
    current_user = runtime.context.get("user")
    service = SearchService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.ns_search(
            query=query,
            page=page,
            size=size,
            only_me=only_me,
            types=types,
            top_k=top_k,
            vector_weight=vector_weight,
            keyword_weight=keyword_weight,
            max_per_parent=max_per_parent,
            use_cache=use_cache,
            current_user=current_user,
        )
        return f"语义检索结果: {result}"
    except Exception as e:
        return f"检索失败: {str(e)}"

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class GlobalSearchSchema(BaseModel):
    """全局搜索参数模型。"""

    q: str = Field(description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")
    only_me: bool = Field(default=False, description="只看我的资源")
    type: str = Field(default="summary", description="结果类型 summary|libraries|movies|user_assets|collections|movie_assets")


class NSSearchSchema(BaseModel):
    """语义搜索参数模型。"""

    query: str = Field(description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")
    only_me: bool = Field(default=False, description="只看我的资源")
    types: Optional[List[str]] = Field(default=None, description="检索域 movies|notes|subtitles")
    top_k: Optional[int] = Field(default=None, ge=1, description="召回上限")
    vector_weight: float = Field(default=0.7, ge=0, le=1, description="向量分权重")
    keyword_weight: float = Field(default=0.3, ge=0, le=1, description="关键词分权重")
    max_per_parent: int = Field(default=2, ge=1, description="同父项最多条数")
    use_cache: bool = Field(default=False, description="是否启用缓存")


@dataclass
class _FallbackUser:
    id: str
    role: str = UserRole.USER


async def _get_current_user(ctx: Optional[RequestContext]) -> Optional[Any]:
    """根据上下文获取当前用户对象。"""
    if ctx is None:
        return None
    try:
        from src.logic.users.user_logic import UserLogic

        logic = UserLogic()
        return await logic.get_user(ctx.user_id)
    except Exception:
        return _FallbackUser(id=ctx.user_id, role=UserRole.USER)


def _get_search_service() -> Any:
    """获取 SearchService 实例。"""
    from src.services.search.search_service import SearchService

    return SearchService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def global_search_tool(
    q: str,
    page: int,
    size: int,
    only_me: bool,
    type: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """执行全局搜索，按类型返回聚合结果。"""
    validated = _validate_schema(
        GlobalSearchSchema,
        q=q,
        page=page,
        size=size,
        only_me=only_me,
        type=type,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_search_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.search(
            q=validated.q,
            page=validated.page,
            size=validated.size,
            only_me=validated.only_me,
            type=validated.type,
            current_user=current_user,
        )
        return f"全局搜索结果: {result}"
    except Exception as e:
        return f"搜索失败: {str(e)}"


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
    ctx: Optional[RequestContext] = None,
) -> str:
    """执行向量+关键词混合检索，支持多域与权重配置。"""
    validated = _validate_schema(
        NSSearchSchema,
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
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_search_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.ns_search(
            query=validated.query,
            page=validated.page,
            size=validated.size,
            only_me=validated.only_me,
            types=validated.types,
            top_k=validated.top_k,
            vector_weight=validated.vector_weight,
            keyword_weight=validated.keyword_weight,
            max_per_parent=validated.max_per_parent,
            use_cache=validated.use_cache,
            current_user=current_user,
        )
        return f"语义检索结果: {result}"
    except Exception as e:
        return f"检索失败: {str(e)}"


def register_search_tools(registry: ToolRegistry) -> None:
    """注册搜索相关工具。"""
    registry.register(
        ToolDefinition(
            name="global_search",
            description="执行全局搜索，按类型返回聚合结果。",
            parameters=_schema(GlobalSearchSchema),
            handler=global_search_tool,
            category="search",
        )
    )
    registry.register(
        ToolDefinition(
            name="ns_search",
            description="执行向量+关键词混合检索，支持多域与权重配置。",
            parameters=_schema(NSSearchSchema),
            handler=ns_search_tool,
            category="search",
        )
    )
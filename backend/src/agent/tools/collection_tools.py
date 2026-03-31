from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import CustomListCreate, CustomListUpdate, UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class ListCollectionsSchema(BaseModel):
    """查询片单列表参数模型。"""

    user_id: Optional[str] = Field(default=None, description="用户ID")
    type: Optional[str] = Field(default=None, description="片单类型")
    query: Optional[str] = Field(default=None, description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=200, description="每页数量")


class GetCollectionSchema(BaseModel):
    """获取片单详情参数模型。"""

    collection_id: str = Field(description="片单ID")


class CreateCollectionSchema(BaseModel):
    """创建片单参数模型。"""

    name: str = Field(description="片单名称")
    type: str = Field(description="片单类型 favorite|watchlist|customlist")
    description: Optional[str] = Field(default=None, description="描述")
    is_public: bool = Field(default=False, description="是否公开")


class UpdateCollectionSchema(BaseModel):
    """更新片单参数模型。"""

    collection_id: str = Field(description="片单ID")
    name: Optional[str] = Field(default=None, description="片单名称")
    description: Optional[str] = Field(default=None, description="描述")
    movies: Optional[List[str]] = Field(default=None, description="电影ID列表")


class DeleteCollectionSchema(BaseModel):
    """删除片单参数模型。"""

    collection_id: str = Field(description="片单ID")


class AddMoviesSchema(BaseModel):
    """添加电影到片单参数模型。"""

    collection_id: str = Field(description="片单ID")
    movie_ids: List[str] = Field(description="电影ID列表")


class RemoveMoviesSchema(BaseModel):
    """从片单移除电影参数模型。"""

    collection_id: str = Field(description="片单ID")
    movie_ids: List[str] = Field(description="电影ID列表")


class GetCollectionMoviesSchema(BaseModel):
    """获取片单电影参数模型。"""

    collection_id: str = Field(description="片单ID")


class InitDefaultCollectionsSchema(BaseModel):
    """初始化默认片单参数模型。"""

    pass


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


def _get_collection_service() -> Any:
    """获取 CollectionService 实例。"""
    from src.services.users.collection_service import CollectionService

    return CollectionService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def list_collections_tool(
    user_id: Optional[str],
    type: Optional[str],
    query: Optional[str],
    page: int,
    page_size: int,
    ctx: Optional[RequestContext] = None,
) -> str:
    """查询片单列表，支持按用户、类型、关键词筛选与分页。"""
    validated = _validate_schema(
        ListCollectionsSchema,
        user_id=user_id,
        type=type,
        query=query,
        page=page,
        page_size=page_size,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_collections(
            user_id=validated.user_id,
            type=validated.type,
            query=validated.query,
            page=validated.page,
            page_size=validated.page_size,
            current_user=current_user,
        )
        return f"片单列表: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def get_collection_tool(
    collection_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取片单详情。"""
    if not collection_id:
        return "参数验证失败: collection_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        collection = await service.get_collection(validated.collection_id, current_user=current_user)
        return f"片单详情: {collection.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def create_collection_tool(
    name: str,
    type: str,
    description: Optional[str],
    is_public: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """创建片单（收藏夹、待看列表或自定义片单）。"""
    validated = _validate_schema(
        CreateCollectionSchema,
        name=name,
        type=type,
        description=description,
        is_public=is_public,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.agent.tools.builders import build_custom_list_create_payload

        data = build_custom_list_create_payload(
            name=validated.name,
            type=validated.type,
            description=validated.description,
            is_public=validated.is_public,
            user_id=current_user.id,
        )
        result = await service.create_collection(data, current_user=current_user)
        return f"片单创建成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


async def update_collection_tool(
    collection_id: str,
    name: Optional[str],
    description: Optional[str],
    movies: Optional[List[str]],
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新片单信息或电影列表。"""
    validated = _validate_schema(
        UpdateCollectionSchema,
        collection_id=collection_id,
        name=name,
        description=description,
        movies=movies,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        patch_payload = {
            "name": validated.name,
            "description": validated.description,
            "movies": validated.movies,
        }
        patch = CustomListUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        result = await service.update_collection(validated.collection_id, patch, current_user=current_user)
        return f"片单更新成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def delete_collection_tool(
    collection_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """删除片单。"""
    if not collection_id:
        return "参数验证失败: collection_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.delete_collection(validated.collection_id, current_user=current_user)
        return f"片单删除成功: {result}"
    except Exception as e:
        return f"删除失败: {str(e)}"


async def add_movies_tool(
    collection_id: str,
    movie_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """添加电影到片单。"""
    validated = _validate_schema(AddMoviesSchema, collection_id=collection_id, movie_ids=movie_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.movie_ids:
        return "参数验证失败: 电影ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.add_movies(validated.collection_id, validated.movie_ids, current_user=current_user)
        return f"电影添加成功: {len(result)} 项"
    except Exception as e:
        return f"添加失败: {str(e)}"


async def remove_movies_tool(
    collection_id: str,
    movie_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """从片单移除电影。"""
    validated = _validate_schema(RemoveMoviesSchema, collection_id=collection_id, movie_ids=movie_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.movie_ids:
        return "参数验证失败: 电影ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.remove_movies(validated.collection_id, validated.movie_ids, current_user=current_user)
        return f"电影移除成功: {len(result)} 项"
    except Exception as e:
        return f"移除失败: {str(e)}"


async def get_collection_movies_tool(
    collection_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取片单中的电影列表。"""
    if not collection_id:
        return "参数验证失败: collection_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_collection_movies(validated.collection_id, current_user=current_user)
        return f"片单电影列表: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def init_default_collections_tool(ctx: Optional[RequestContext] = None) -> str:
    """为用户初始化默认片单（收藏夹、待看列表）。"""
    current_user = await _get_current_user(ctx)
    service = _get_collection_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.init_default_collections(current_user=current_user)
        return f"默认片单初始化成功: {result}"
    except Exception as e:
        return f"初始化失败: {str(e)}"


def register_collection_tools(registry: ToolRegistry) -> None:
    """注册片单相关工具。"""
    registry.register(
        ToolDefinition(
            name="list_collections",
            description="查询片单列表，支持按用户、类型、关键词筛选与分页。",
            parameters=_schema(ListCollectionsSchema),
            handler=list_collections_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_collection",
            description="获取片单详情。",
            parameters=_schema(GetCollectionSchema),
            handler=get_collection_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_collection",
            description="创建片单（收藏夹、待看列表或自定义片单）。",
            parameters=_schema(CreateCollectionSchema),
            handler=create_collection_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_collection",
            description="更新片单信息或电影列表。",
            parameters=_schema(UpdateCollectionSchema),
            handler=update_collection_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_collection",
            description="删除片单。",
            parameters=_schema(DeleteCollectionSchema),
            handler=delete_collection_tool,
            category="collections",
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="add_movies",
            description="添加电影到片单。",
            parameters=_schema(AddMoviesSchema),
            handler=add_movies_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="remove_movies",
            description="从片单移除电影。",
            parameters=_schema(RemoveMoviesSchema),
            handler=remove_movies_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_collection_movies",
            description="获取片单中的电影列表。",
            parameters=_schema(GetCollectionMoviesSchema),
            handler=get_collection_movies_tool,
            category="collections",
        )
    )
    registry.register(
        ToolDefinition(
            name="init_default_collections",
            description="为用户初始化默认片单（收藏夹、待看列表）。",
            parameters=_schema(InitDefaultCollectionsSchema),
            handler=init_default_collections_tool,
            category="collections",
        )
    )

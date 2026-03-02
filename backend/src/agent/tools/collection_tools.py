from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
from src.services.users.collection_service import CollectionService
from src.agent.tools.builders import build_custom_list_create_payload


class ListCollectionsSchema(BaseModel):
    user_id: Optional[str] = Field(default=None, description="用户ID")
    type: Optional[str] = Field(default=None, description="片单类型")
    query: Optional[str] = Field(default=None, description="搜索关键词")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=20, description="每页数量")


class GetCollectionSchema(BaseModel):
    collection_id: str = Field(description="片单ID")


class CreateCollectionSchema(BaseModel):
    name: str = Field(description="片单名称")
    type: str = Field(description="片单类型 favorite|watchlist|customlist")
    description: Optional[str] = Field(default=None, description="描述")
    is_public: bool = Field(default=False, description="是否公开")


class UpdateCollectionSchema(BaseModel):
    collection_id: str = Field(description="片单ID")
    name: Optional[str] = Field(default=None, description="片单名称")
    description: Optional[str] = Field(default=None, description="描述")
    movies: Optional[List[str]] = Field(default=None, description="电影ID列表")


class DeleteCollectionSchema(BaseModel):
    collection_id: str = Field(description="片单ID")


class AddMoviesSchema(BaseModel):
    collection_id: str = Field(description="片单ID")
    movie_ids: List[str] = Field(description="电影ID列表")


class RemoveMoviesSchema(BaseModel):
    collection_id: str = Field(description="片单ID")
    movie_ids: List[str] = Field(description="电影ID列表")


class GetCollectionMoviesSchema(BaseModel):
    collection_id: str = Field(description="片单ID")


class InitDefaultCollectionsSchema(BaseModel):
    pass


@tool(args_schema=ListCollectionsSchema)
async def list_collections_tool(
    user_id: Optional[str],
    type: Optional[str],
    query: Optional[str],
    page: int,
    page_size: int,
    runtime: ToolRuntime,
) -> str:
    """按条件列出片单，支持用户、类型、关键词筛选与分页。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import CustomListType
        t = CustomListType(type) if type else None
        result = await service.list_collections(
            user_id=user_id,
            type_filter=t,
            query=query,
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
        return f"片单列表: {result.model_dump()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=GetCollectionSchema)
async def get_collection_tool(
    collection_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取片单详情。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_collection(collection_id, current_user=current_user)
        return f"片单详情: {result.model_dump() if result else None}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=CreateCollectionSchema)
async def create_collection_tool(
    name: str,
    type: str,
    description: Optional[str],
    is_public: bool,
    runtime: ToolRuntime,
) -> str:
    """创建片单（收藏、想看或自定义）。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        # 使用统一的构造函数，复用HTTP路由的逻辑
        data = build_custom_list_create_payload(
            name=name,
            type=type,
            description=description,
            is_public=is_public,
            movies=[],
            user_id=current_user.id
        )
        created = await service.create_collection(data, current_user=current_user)
        return f"片单创建成功: {created.id}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


@tool(args_schema=UpdateCollectionSchema)
async def update_collection_tool(
    collection_id: str,
    name: Optional[str],
    description: Optional[str],
    movies: Optional[List[str]],
    runtime: ToolRuntime,
) -> str:
    """更新片单基本信息或影片列表。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import CustomListUpdate
        data = CustomListUpdate(name=name, description=description, movies=movies)
        updated = await service.update_collection(collection_id, data, current_user=current_user)
        return f"片单更新成功: {updated.model_dump() if updated else None}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


@tool(args_schema=DeleteCollectionSchema)
async def delete_collection_tool(
    collection_id: str,
    runtime: ToolRuntime,
) -> str:
    """删除片单。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        deleted = await service.delete_collection(collection_id, current_user=current_user)
        return f"片单删除成功: {deleted.model_dump() if deleted else None}"
    except Exception as e:
        return f"删除失败: {str(e)}"


@tool(args_schema=AddMoviesSchema)
async def add_movies_to_collection_tool(
    collection_id: str,
    movie_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """向片单中添加影片。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.add_movies(collection_id, movie_ids, current_user=current_user)
        return f"添加影片成功: {result}"
    except Exception as e:
        return f"添加失败: {str(e)}"


@tool(args_schema=RemoveMoviesSchema)
async def remove_movies_from_collection_tool(
    collection_id: str,
    movie_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """从片单中移除影片。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.remove_movies(collection_id, movie_ids, current_user=current_user)
        return f"移除影片成功: {result}"
    except Exception as e:
        return f"移除失败: {str(e)}"


@tool(args_schema=GetCollectionMoviesSchema)
async def get_collection_movies_tool(
    collection_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取片单包含的影片列表。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        movies = await service.get_collection_movies(collection_id, current_user=current_user)
        return f"片单影片: {movies}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=InitDefaultCollectionsSchema)
async def init_user_default_collections_tool(
    runtime: ToolRuntime,
) -> str:
    """为当前用户初始化默认片单。"""
    current_user = runtime.context.get("user")
    service = CollectionService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        items = await service.init_user_default_collections(current_user=current_user)
        return f"默认片单初始化成功: {[i.id for i in items]}"
    except Exception as e:
        return f"初始化失败: {str(e)}"

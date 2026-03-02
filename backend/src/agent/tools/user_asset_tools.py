from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List, Tuple, Dict
from src.services.users.asset_service import AssetService
from src.agent.tools.builders import build_user_asset_create_payload


class ListUserAssetsSchema(BaseModel):
    query: Optional[str] = Field(default=None, description="搜索关键词")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    movie_ids: Optional[List[str]] = Field(default=None, description="电影ID列表")
    asset_type: Optional[List[str]] = Field(default=None, description="资产类型")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    is_public: Optional[bool] = Field(default=None, description="是否公开")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")
    sort_by: Optional[str] = Field(default=None, description="排序字段")
    sort_dir: Optional[int] = Field(default=None, description="排序方向 1/-1")
    is_deleted: Optional[bool] = Field(default=False, description="是否已删除")


class GetUserAssetSchema(BaseModel):
    asset_id: str = Field(description="用户资产ID")


class UploadUserAssetSchema(BaseModel):
    movie_id: str = Field(description="电影ID")
    type: str = Field(description="资产类型 screenshot|clip")
    name: Optional[str] = Field(default=None, description="名称")
    related_movie_ids: Optional[List[str]] = Field(default=None, description="关联电影")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    is_public: bool = Field(default=False, description="是否公开")
    local_path: str = Field(description="本地文件路径")


class CreateTextUserAssetSchema(BaseModel):
    movie_id: str = Field(description="电影ID")
    type: str = Field(description="资产类型 note|review")
    name: Optional[str] = Field(default=None, description="名称")
    related_movie_ids: Optional[List[str]] = Field(default=None, description="关联电影")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    is_public: bool = Field(default=False, description="是否公开")
    content: str = Field(description="文本内容")


class UpdateUserAssetSchema(BaseModel):
    asset_id: str = Field(description="用户资产ID")
    name: str = Field(description="名称")
    related_movie_ids: Optional[List[str]] = Field(default=None, description="关联电影")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    content: Optional[str] = Field(default=None, description="文本内容")


class DeleteUserAssetsSchema(BaseModel):
    asset_ids: List[str] = Field(description="资产ID列表")
    soft_delete: bool = Field(default=True, description="是否软删除")


class RestoreUserAssetsSchema(BaseModel):
    asset_ids: List[str] = Field(description="资产ID列表")


class ListIsolatedAssetsSchema(BaseModel):
    pass


class ListUserAssetThumbnailsSignedSchema(BaseModel):
    asset_ids: List[str] = Field(description="资产ID列表")


@tool(args_schema=ListUserAssetsSchema)
async def list_user_assets_tool(
    query: Optional[str],
    user_id: Optional[str],
    movie_ids: Optional[List[str]],
    asset_type: Optional[List[str]],
    tags: Optional[List[str]],
    is_public: Optional[bool],
    page: int,
    size: int,
    sort_by: Optional[str],
    sort_dir: Optional[int],
    is_deleted: Optional[bool],
    runtime: ToolRuntime,
) -> str:
    """按条件列出用户资产（截图、剪辑、笔记等）。支持分页与排序。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import UserAssetType
        sort: Optional[List[Tuple[str, int]]] = None
        if sort_by and sort_dir:
            sort = [(sort_by, sort_dir)]
        types = [UserAssetType(t) for t in asset_type] if asset_type else []
        result = await service.list_assets(
            query=query,
            user_id=user_id,
            movie_ids=movie_ids,
            asset_type=types,
            tags=tags,
            is_public=is_public,
            page=page,
            size=size,
            sort=sort,
            projection=None,
            is_deleted=is_deleted,
            current_user=current_user,
        )
        payload = result.model_dump() if hasattr(result, "model_dump") else result
        return f"用户资产列表: {payload}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=GetUserAssetSchema)
async def get_user_asset_tool(
    asset_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取用户资产详情。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        asset = await service.get_asset(asset_id, current_user=current_user)
        return f"用户资产详情: {asset.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=UploadUserAssetSchema)
async def upload_user_asset_tool(
    movie_id: str,
    type: str,
    name: Optional[str],
    related_movie_ids: Optional[List[str]],
    tags: Optional[List[str]],
    is_public: bool,
    local_path: str,
    runtime: ToolRuntime,
) -> str:
    """上传用户资产文件（本地路径）。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import UserAssetCreate, UserAssetType, AssetStoreType
        payload = UserAssetCreate(
            movie_id=movie_id,
            type=UserAssetType(type),
            name=name or "temp",
            related_movie_ids=related_movie_ids or [],
            tags=tags or [],
            is_public=is_public,
            permissions=[],
            path="placeholder",
            store_type=AssetStoreType.LOCAL,
            actual_path=None,
            content=None,
            user_id=current_user.id,
        )
        created, tasks = await service.upload_user_asset(
            payload,
            current_user=current_user,
            context={"local_path": local_path},
        )
        return f"用户资产上传成功: {created.id}, 任务: {tasks}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"上传失败: {str(e)}"


@tool(args_schema=CreateTextUserAssetSchema)
async def create_text_user_asset_tool(
    movie_id: str,
    type: str,
    name: Optional[str],
    related_movie_ids: Optional[List[str]],
    tags: Optional[List[str]],
    is_public: bool,
    content: str,
    runtime: ToolRuntime,
) -> str:
    """创建文本类用户资产（笔记、影评）。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        # 使用统一的构造函数，复用HTTP路由的逻辑
        payload = build_user_asset_create_payload(
            movie_id=movie_id,
            type=type,
            name=name,
            content=content,
            related_movie_ids=related_movie_ids,
            tags=tags,
            is_public=is_public,
            user_id=current_user.id
        )
        created = await service.create_text_user_asset(payload, current_user=current_user)
        return f"文本资产创建成功: {created.id}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


@tool(args_schema=UpdateUserAssetSchema)
async def update_user_asset_tool(
    asset_id: str,
    name: str,
    related_movie_ids: Optional[List[str]],
    tags: Optional[List[str]],
    content: Optional[str],
    runtime: ToolRuntime,
) -> str:
    """更新用户资产的基础信息或内容。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import UserAssetUpdate
        patch = UserAssetUpdate(
            name=name,
            related_movie_ids=related_movie_ids,
            tags=tags,
            content=content,
        )
        updated = await service.update_user_asset(asset_id, patch, current_user=current_user)
        return f"用户资产更新成功: {updated.model_dump()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


@tool(args_schema=DeleteUserAssetsSchema)
async def delete_user_assets_tool(
    asset_ids: List[str],
    soft_delete: bool,
    runtime: ToolRuntime,
) -> str:
    """批量删除用户资产，支持软删除。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        count = await service.delete_user_assets(asset_ids, soft_delete=soft_delete, current_user=current_user)
        return f"删除完成: 成功 {count} 项"
    except Exception as e:
        return f"删除失败: {str(e)}"


@tool(args_schema=RestoreUserAssetsSchema)
async def restore_user_assets_tool(
    asset_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """批量恢复已删除的用户资产。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        restored = await service.restore_user_assets(asset_ids, current_user=current_user)
        return f"恢复成功: {len(restored)} 项"
    except Exception as e:
        return f"恢复失败: {str(e)}"


@tool(args_schema=ListIsolatedAssetsSchema)
async def list_isolated_user_assets_tool(
    runtime: ToolRuntime,
) -> str:
    """列出未被引用的孤立用户资产。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        items = await service.list_isolated_assets(current_user=current_user)
        data = [i.model_dump() if hasattr(i, "model_dump") else i for i in items]
        return f"孤立资产列表: {data}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=ListUserAssetThumbnailsSignedSchema)
async def list_user_asset_thumbnails_signed_tool(
    asset_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """获取用户资产缩略图的签名访问URL。"""
    current_user = runtime.context.get("user")
    service = AssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        urls = await service.list_user_asset_thumbnails_signed(asset_ids, current_user=current_user)
        return f"缩略图签名URL: {urls}"
    except Exception as e:
        return f"获取失败: {str(e)}"

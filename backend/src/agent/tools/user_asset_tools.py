from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from src.models import UserAssetCreate, UserAssetUpdate, UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class ListUserAssetsSchema(BaseModel):
    """查询用户资产列表参数模型。"""

    query: Optional[str] = Field(default=None, description="搜索关键词")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    movie_ids: Optional[List[str]] = Field(default=None, description="电影ID列表")
    asset_type: Optional[List[str]] = Field(default=None, description="资产类型")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    is_public: Optional[bool] = Field(default=None, description="是否公开")
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")
    sort_by: Optional[str] = Field(default=None, description="排序字段")
    sort_dir: Optional[int] = Field(default=None, description="排序方向 1/-1")
    is_deleted: Optional[bool] = Field(default=False, description="是否已删除")


class GetUserAssetSchema(BaseModel):
    """获取用户资产详情参数模型。"""

    asset_id: str = Field(description="用户资产ID")


class UploadUserAssetSchema(BaseModel):
    """上传用户资产参数模型。"""

    movie_id: str = Field(description="电影ID")
    type: str = Field(description="资产类型 screenshot|clip")
    name: Optional[str] = Field(default=None, description="名称")
    related_movie_ids: Optional[List[str]] = Field(default=None, description="关联电影")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    is_public: bool = Field(default=False, description="是否公开")
    local_path: str = Field(description="本地文件路径")


class CreateTextUserAssetSchema(BaseModel):
    """创建文本用户资产参数模型。"""

    movie_id: str = Field(description="电影ID")
    type: str = Field(description="资产类型 note|review")
    name: Optional[str] = Field(default=None, description="名称")
    related_movie_ids: Optional[List[str]] = Field(default=None, description="关联电影")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    is_public: bool = Field(default=False, description="是否公开")
    content: str = Field(description="文本内容")


class UpdateUserAssetSchema(BaseModel):
    """更新用户资产参数模型。"""

    asset_id: str = Field(description="用户资产ID")
    name: str = Field(description="名称")
    related_movie_ids: Optional[List[str]] = Field(default=None, description="关联电影")
    tags: Optional[List[str]] = Field(default=None, description="标签")
    content: Optional[str] = Field(default=None, description="文本内容")


class DeleteUserAssetsSchema(BaseModel):
    """删除用户资产参数模型。"""

    asset_ids: List[str] = Field(description="资产ID列表")
    soft_delete: bool = Field(default=True, description="是否软删除")


class RestoreUserAssetsSchema(BaseModel):
    """恢复用户资产参数模型。"""

    asset_ids: List[str] = Field(description="资产ID列表")


class ListIsolatedAssetsSchema(BaseModel):
    """查询独立资产参数模型。"""

    pass


class ListUserAssetThumbnailsSignedSchema(BaseModel):
    """获取用户资产缩略图签名参数模型。"""

    asset_ids: List[str] = Field(description="资产ID列表")


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


def _get_asset_service() -> Any:
    """获取 AssetService 实例。"""
    from src.services.users.asset_service import AssetService

    return AssetService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


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
    ctx: Optional[RequestContext] = None,
) -> str:
    """按条件列出用户资产（截图、剪辑、笔记等）。支持分页与排序。"""
    validated = _validate_schema(
        ListUserAssetsSchema,
        query=query,
        user_id=user_id,
        movie_ids=movie_ids,
        asset_type=asset_type,
        tags=tags,
        is_public=is_public,
        page=page,
        size=size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        is_deleted=is_deleted,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if validated.sort_dir not in (None, 1, -1):
        return "参数验证失败: sort_dir 仅支持 1 或 -1"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import UserAssetType

        sort: Optional[List[Tuple[str, int]]] = None
        if validated.sort_by and validated.sort_dir:
            sort = [(validated.sort_by, validated.sort_dir)]
        types = [UserAssetType(t) for t in validated.asset_type] if validated.asset_type else []
        result = await service.list_assets(
            query=validated.query,
            user_id=validated.user_id,
            movie_ids=validated.movie_ids,
            asset_type=types,
            tags=validated.tags,
            is_public=validated.is_public,
            page=validated.page,
            size=validated.size,
            sort=sort,
            projection=None,
            is_deleted=validated.is_deleted,
            current_user=current_user,
        )
        payload = result.model_dump() if hasattr(result, "model_dump") else result
        return f"用户资产列表: {payload}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def get_user_asset_tool(
    asset_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取用户资产详情。"""
    if not asset_id:
        return "参数验证失败: asset_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        asset = await service.get_asset(asset_id, current_user=current_user)
        return f"用户资产详情: {asset.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def upload_user_asset_tool(
    movie_id: str,
    type: str,
    name: Optional[str],
    related_movie_ids: Optional[List[str]],
    tags: Optional[List[str]],
    is_public: bool,
    local_path: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """上传用户资产文件（本地路径）。"""
    validated = _validate_schema(
        UploadUserAssetSchema,
        movie_id=movie_id,
        type=type,
        name=name,
        related_movie_ids=related_movie_ids,
        tags=tags,
        is_public=is_public,
        local_path=local_path,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.agent.tools.builders import build_user_asset_create_payload

        data = build_user_asset_create_payload(
            movie_id=validated.movie_id,
            type=validated.type,
            name=validated.name,
            related_movie_ids=validated.related_movie_ids,
            tags=validated.tags,
            is_public=validated.is_public,
            local_path=validated.local_path,
            user_id=current_user.id,
        )
        result = await service.create_asset(data, current_user=current_user)
        return f"用户资产上传成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"上传失败: {str(e)}"


async def create_text_user_asset_tool(
    movie_id: str,
    type: str,
    name: Optional[str],
    related_movie_ids: Optional[List[str]],
    tags: Optional[List[str]],
    is_public: bool,
    content: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """创建文本用户资产（笔记、评论等）。"""
    validated = _validate_schema(
        CreateTextUserAssetSchema,
        movie_id=movie_id,
        type=type,
        name=name,
        related_movie_ids=related_movie_ids,
        tags=tags,
        is_public=is_public,
        content=content,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.agent.tools.builders import build_user_asset_create_payload

        data = build_user_asset_create_payload(
            movie_id=validated.movie_id,
            type=validated.type,
            name=validated.name,
            related_movie_ids=validated.related_movie_ids,
            tags=validated.tags,
            is_public=validated.is_public,
            content=validated.content,
            user_id=current_user.id,
        )
        result = await service.create_asset(data, current_user=current_user)
        return f"文本用户资产创建成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


async def update_user_asset_tool(
    asset_id: str,
    name: str,
    related_movie_ids: Optional[List[str]],
    tags: Optional[List[str]],
    content: Optional[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新用户资产信息。"""
    validated = _validate_schema(
        UpdateUserAssetSchema,
        asset_id=asset_id,
        name=name,
        related_movie_ids=related_movie_ids,
        tags=tags,
        content=content,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        patch_payload = {
            "name": validated.name,
            "related_movie_ids": validated.related_movie_ids,
            "tags": validated.tags,
            "content": validated.content,
        }
        patch = UserAssetUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        result = await service.update_asset(validated.asset_id, patch, current_user=current_user)
        return f"用户资产更新成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def delete_user_assets_tool(
    asset_ids: List[str],
    soft_delete: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量删除用户资产，支持软删除。"""
    validated = _validate_schema(DeleteUserAssetsSchema, asset_ids=asset_ids, soft_delete=soft_delete)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.asset_ids:
        return "参数验证失败: 资产ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.delete_assets(
            validated.asset_ids, soft_delete=validated.soft_delete, current_user=current_user
        )
        return f"删除完成: {result}"
    except Exception as e:
        return f"删除失败: {str(e)}"


async def restore_user_assets_tool(
    asset_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量恢复已删除用户资产。"""
    validated = _validate_schema(RestoreUserAssetsSchema, asset_ids=asset_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.asset_ids:
        return "参数验证失败: 资产ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.restore_assets(validated.asset_ids, current_user=current_user)
        return f"恢复成功: {len(result)} 项"
    except Exception as e:
        return f"恢复失败: {str(e)}"


async def list_isolated_assets_tool(ctx: Optional[RequestContext] = None) -> str:
    """查询独立资产。"""
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_isolated_assets(current_user=current_user)
        return f"独立资产列表: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def list_user_asset_thumbnails_signed_tool(
    asset_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取用户资产缩略图签名。"""
    validated = _validate_schema(ListUserAssetThumbnailsSignedSchema, asset_ids=asset_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.asset_ids:
        return "参数验证失败: 资产ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_thumbnails_signed(validated.asset_ids, current_user=current_user)
        return f"缩略图签名列表: {result}"
    except Exception as e:
        return f"获取失败: {str(e)}"


def register_user_asset_tools(registry: ToolRegistry) -> None:
    """注册用户资产相关工具。"""
    registry.register(
        ToolDefinition(
            name="list_user_assets",
            description="按条件列出用户资产（截图、剪辑、笔记等）。支持分页与排序。",
            parameters=_schema(ListUserAssetsSchema),
            handler=list_user_assets_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_user_asset",
            description="获取用户资产详情。",
            parameters=_schema(GetUserAssetSchema),
            handler=get_user_asset_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="upload_user_asset",
            description="上传用户资产文件（本地路径）。",
            parameters=_schema(UploadUserAssetSchema),
            handler=upload_user_asset_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_text_user_asset",
            description="创建文本用户资产（笔记、评论等）。",
            parameters=_schema(CreateTextUserAssetSchema),
            handler=create_text_user_asset_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_user_asset",
            description="更新用户资产信息。",
            parameters=_schema(UpdateUserAssetSchema),
            handler=update_user_asset_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_user_assets",
            description="批量删除用户资产，支持软删除。",
            parameters=_schema(DeleteUserAssetsSchema),
            handler=delete_user_assets_tool,
            category="user_assets",
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="restore_user_assets",
            description="批量恢复已删除用户资产。",
            parameters=_schema(RestoreUserAssetsSchema),
            handler=restore_user_assets_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_isolated_assets",
            description="查询独立资产。",
            parameters=_schema(ListIsolatedAssetsSchema),
            handler=list_isolated_assets_tool,
            category="user_assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_user_asset_thumbnails_signed",
            description="获取用户资产缩略图签名。",
            parameters=_schema(ListUserAssetThumbnailsSignedSchema),
            handler=list_user_asset_thumbnails_signed_tool,
            category="user_assets",
        )
    )

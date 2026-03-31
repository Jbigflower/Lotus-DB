from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import AssetCreate, AssetUpdate, UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class ListMovieAssetsPageSchema(BaseModel):
    """分页查询电影资产列表参数模型。"""

    movie_id: str = Field(description="电影ID")
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")


class UploadMovieAssetSchema(BaseModel):
    """上传电影资产参数模型。"""

    library_id: str = Field(description="媒体库ID")
    movie_id: str = Field(description="电影ID")
    type: str = Field(description="资产类型 video|subtitle|image")
    name: Optional[str] = Field(default=None, description="资产名称")
    url: Optional[str] = Field(default=None, description="下载地址")
    local_path: Optional[str] = Field(default=None, description="本地文件路径")
    source_ext: Optional[str] = Field(default=None, description="源文件扩展名")


class UpdateMovieAssetSchema(BaseModel):
    """更新电影资产参数模型。"""

    asset_id: str = Field(description="资产ID")
    name: Optional[str] = Field(default=None, description="资产名称")
    description: Optional[str] = Field(default=None, description="描述")
    tags: Optional[List[str]] = Field(default=None, description="标签")


class DeleteMovieAssetsSchema(BaseModel):
    """删除电影资产参数模型。"""

    asset_ids: List[str] = Field(description="资产ID列表")
    soft_delete: bool = Field(default=True, description="是否软删除")


class RestoreMovieAssetsSchema(BaseModel):
    """恢复电影资产参数模型。"""

    asset_ids: List[str] = Field(description="资产ID列表")


class ListRecycleBinAssetsSchema(BaseModel):
    """查询回收站资产参数模型。"""

    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")


class ListAssetThumbnailsSignedSchema(BaseModel):
    """获取资产缩略图签名参数模型。"""

    asset_ids: List[str] = Field(description="资产ID列表")


class GetAssetSchema(BaseModel):
    """获取资产详情参数模型。"""

    asset_id: str = Field(description="资产ID")


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
    """获取 MovieAssetService 实例。"""
    from src.services.movies.asset_service import MovieAssetService

    return MovieAssetService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def list_movie_assets_page_tool(
    movie_id: str,
    page: int,
    size: int,
    ctx: Optional[RequestContext] = None,
) -> str:
    """分页列出电影关联的资产（视频、字幕、图片等）。"""
    validated = _validate_schema(ListMovieAssetsPageSchema, movie_id=movie_id, page=page, size=size)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_movie_assets_page(validated.movie_id, page=validated.page, size=validated.size, current_user=current_user)
        return f"电影资产分页: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def upload_movie_asset_tool(
    library_id: str,
    movie_id: str,
    type: str,
    name: Optional[str],
    url: Optional[str],
    local_path: Optional[str],
    source_ext: Optional[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """为电影上传资产，支持本地文件或URL来源。"""
    validated = _validate_schema(
        UploadMovieAssetSchema,
        library_id=library_id,
        movie_id=movie_id,
        type=type,
        name=name,
        url=url,
        local_path=local_path,
        source_ext=source_ext,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.agent.tools.builders import build_asset_create_payload

        payload = build_asset_create_payload(
            library_id=validated.library_id,
            movie_id=validated.movie_id,
            type=validated.type,
            name=validated.name or "",
            store_type="Local",
        )
        context = {}
        if validated.url:
            context["url"] = validated.url
        if validated.local_path:
            context["local_path"] = validated.local_path
        if validated.source_ext:
            context["source_ext"] = validated.source_ext
        created, tasks = await service.upload_movie_asset(payload, current_user=current_user, context=context)
        return f"资产上传成功: {created.id}, 任务: {tasks}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"上传失败: {str(e)}"


async def update_movie_asset_tool(
    asset_id: str,
    name: Optional[str],
    description: Optional[str],
    tags: Optional[List[str]],
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新电影资产的名称、描述或标签。"""
    validated = _validate_schema(
        UpdateMovieAssetSchema,
        asset_id=asset_id,
        name=name,
        description=description,
        tags=tags,
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
            "description": validated.description,
            "tags": validated.tags,
        }
        patch = AssetUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        updated = await service.update_movie_asset(validated.asset_id, patch, current_user=current_user)
        return f"资产更新成功: {updated.model_dump()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def delete_movie_assets_tool(
    asset_ids: List[str],
    soft_delete: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量删除电影资产，支持软删除。"""
    validated = _validate_schema(DeleteMovieAssetsSchema, asset_ids=asset_ids, soft_delete=soft_delete)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.asset_ids:
        return "参数验证失败: 资产ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        count = await service.delete_movie_assets(validated.asset_ids, current_user=current_user, soft_delete=validated.soft_delete)
        return f"删除完成: 成功 {count} 项"
    except Exception as e:
        return f"删除失败: {str(e)}"


async def restore_movie_assets_tool(
    asset_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量恢复已删除的电影资产。"""
    validated = _validate_schema(RestoreMovieAssetsSchema, asset_ids=asset_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.asset_ids:
        return "参数验证失败: 资产ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        restored = await service.restore_movie_assets(validated.asset_ids, current_user=current_user)
        return f"恢复成功: {len(restored)} 项"
    except Exception as e:
        return f"恢复失败: {str(e)}"


async def list_recycle_bin_assets_tool(
    page: int,
    size: int,
    ctx: Optional[RequestContext] = None,
) -> str:
    """分页查看回收站中的电影资产。"""
    validated = _validate_schema(ListRecycleBinAssetsSchema, page=page, size=size)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_recycle_bin_assets(page=validated.page, size=validated.size, current_user=current_user)
        return f"回收站资产: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def list_asset_thumbnails_signed_tool(
    asset_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取资产缩略图的签名访问URL。"""
    validated = _validate_schema(ListAssetThumbnailsSignedSchema, asset_ids=asset_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.asset_ids:
        return "参数验证失败: 资产ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        urls = await service.list_asset_thumbnails_signed(validated.asset_ids, current_user=current_user)
        return f"缩略图签名URL: {urls}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def get_movie_asset_tool(
    asset_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取单个电影资产的详情。"""
    if not asset_id:
        return "参数验证失败: asset_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_asset_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        asset = await service.get_asset(asset_id, current_user=current_user)
        return f"电影资产详情: {asset.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


def register_asset_tools(registry: ToolRegistry) -> None:
    """注册资产相关工具。"""
    registry.register(
        ToolDefinition(
            name="list_movie_assets_page",
            description="分页列出电影关联的资产（视频、字幕、图片等）。",
            parameters=_schema(ListMovieAssetsPageSchema),
            handler=list_movie_assets_page_tool,
            category="assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="upload_movie_asset",
            description="为电影上传资产，支持本地文件或URL来源。",
            parameters=_schema(UploadMovieAssetSchema),
            handler=upload_movie_asset_tool,
            category="assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_movie_asset",
            description="更新电影资产的名称、描述或标签。",
            parameters=_schema(UpdateMovieAssetSchema),
            handler=update_movie_asset_tool,
            category="assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_movie_assets",
            description="批量删除电影资产，支持软删除。",
            parameters=_schema(DeleteMovieAssetsSchema),
            handler=delete_movie_assets_tool,
            category="assets",
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="restore_movie_assets",
            description="批量恢复已删除的电影资产。",
            parameters=_schema(RestoreMovieAssetsSchema),
            handler=restore_movie_assets_tool,
            category="assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_recycle_bin_assets",
            description="分页查看回收站中的电影资产。",
            parameters=_schema(ListRecycleBinAssetsSchema),
            handler=list_recycle_bin_assets_tool,
            category="assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_asset_thumbnails_signed",
            description="获取资产缩略图的签名访问URL。",
            parameters=_schema(ListAssetThumbnailsSignedSchema),
            handler=list_asset_thumbnails_signed_tool,
            category="assets",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_movie_asset",
            description="获取单个电影资产的详情。",
            parameters=_schema(GetAssetSchema),
            handler=get_movie_asset_tool,
            category="assets",
        )
    )

from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
from src.services.movies.asset_service import MovieAssetService
from src.agent.tools.builders import build_asset_create_payload


class ListMovieAssetsPageSchema(BaseModel):
    movie_id: str = Field(description="电影ID")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")


class UploadMovieAssetSchema(BaseModel):
    library_id: str = Field(description="媒体库ID")
    movie_id: str = Field(description="电影ID")
    type: str = Field(description="资产类型 video|subtitle|image")
    name: Optional[str] = Field(default=None, description="资产名称")
    url: Optional[str] = Field(default=None, description="下载地址")
    local_path: Optional[str] = Field(default=None, description="本地文件路径")
    source_ext: Optional[str] = Field(default=None, description="源文件扩展名")


class UpdateMovieAssetSchema(BaseModel):
    asset_id: str = Field(description="资产ID")
    name: Optional[str] = Field(default=None, description="资产名称")
    description: Optional[str] = Field(default=None, description="描述")
    tags: Optional[List[str]] = Field(default=None, description="标签")


class DeleteMovieAssetsSchema(BaseModel):
    asset_ids: List[str] = Field(description="资产ID列表")
    soft_delete: bool = Field(default=True, description="是否软删除")


class RestoreMovieAssetsSchema(BaseModel):
    asset_ids: List[str] = Field(description="资产ID列表")


class ListRecycleBinAssetsSchema(BaseModel):
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")


class ListAssetThumbnailsSignedSchema(BaseModel):
    asset_ids: List[str] = Field(description="资产ID列表")


class GetAssetSchema(BaseModel):
    asset_id: str = Field(description="资产ID")


@tool(args_schema=ListMovieAssetsPageSchema)
async def list_movie_assets_page_tool(
    movie_id: str,
    page: int,
    size: int,
    runtime: ToolRuntime,
) -> str:
    """分页列出电影关联的资产（视频、字幕、图片等）。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_movie_assets_page(movie_id, page=page, size=size, current_user=current_user)
        return f"电影资产分页: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=UploadMovieAssetSchema)
async def upload_movie_asset_tool(
    library_id: str,
    movie_id: str,
    type: str,
    name: Optional[str],
    url: Optional[str],
    local_path: Optional[str],
    source_ext: Optional[str],
    runtime: ToolRuntime,
) -> str:
    """为电影上传资产，支持本地文件或URL来源。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        # 使用统一的构造函数，复用HTTP路由的逻辑
        payload = build_asset_create_payload(
            library_id=library_id,
            movie_id=movie_id,
            type=type,
            name=name or "",
            store_type="Local"
        )
        context = {}
        if url:
            context["url"] = url
        if local_path:
            context["local_path"] = local_path
        if source_ext:
            context["source_ext"] = source_ext
        created, tasks = await service.upload_movie_asset(payload, current_user=current_user, context=context)
        return f"资产上传成功: {created.id}, 任务: {tasks}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"上传失败: {str(e)}"


@tool(args_schema=UpdateMovieAssetSchema)
async def update_movie_asset_tool(
    asset_id: str,
    name: Optional[str],
    description: Optional[str],
    tags: Optional[List[str]],
    runtime: ToolRuntime,
) -> str:
    """更新电影资产的名称、描述或标签。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import AssetUpdate
        patch = AssetUpdate(name=name, description=description, tags=tags)
        updated = await service.update_movie_asset(asset_id, patch, current_user=current_user)
        return f"资产更新成功: {updated.model_dump()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


@tool(args_schema=DeleteMovieAssetsSchema)
async def delete_movie_assets_tool(
    asset_ids: List[str],
    soft_delete: bool,
    runtime: ToolRuntime,
) -> str:
    """批量删除电影资产，支持软删除。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        count = await service.delete_movie_assets(asset_ids, current_user=current_user, soft_delete=soft_delete)
        return f"删除完成: 成功 {count} 项"
    except Exception as e:
        return f"删除失败: {str(e)}"


@tool(args_schema=RestoreMovieAssetsSchema)
async def restore_movie_assets_tool(
    asset_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """批量恢复已删除的电影资产。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        restored = await service.restore_movie_assets(asset_ids, current_user=current_user)
        return f"恢复成功: {len(restored)} 项"
    except Exception as e:
        return f"恢复失败: {str(e)}"


@tool(args_schema=ListRecycleBinAssetsSchema)
async def list_recycle_bin_assets_tool(
    page: int,
    size: int,
    runtime: ToolRuntime,
) -> str:
    """分页查看回收站中的电影资产。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_recycle_bin_assets(page=page, size=size, current_user=current_user)
        return f"回收站资产: {result.model_dump() if hasattr(result, 'model_dump') else result}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=ListAssetThumbnailsSignedSchema)
async def list_asset_thumbnails_signed_tool(
    asset_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """获取资产缩略图的签名访问URL。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        urls = await service.list_asset_thumbnails_signed(asset_ids, current_user=current_user)
        return f"缩略图签名URL: {urls}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=GetAssetSchema)
async def get_movie_asset_tool(
    asset_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取单个电影资产的详情。"""
    current_user = runtime.context.get("user")
    service = MovieAssetService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        asset = await service.get_asset(asset_id, current_user=current_user)
        return f"电影资产详情: {asset.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import LibraryCreate, LibraryUpdate, UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class CreateLibrarySchema(BaseModel):
    """创建媒体库参数模型。"""

    name: str = Field(description="媒体库名称")
    type: str = Field(description="媒体库类型，目前只支持 'movie' 或 'tv'")
    description: str = Field(description="媒体库的详细描述")
    is_public: bool = Field(default=False, description="是否公开可见")
    metadata_plugins: Optional[List[str]] = Field(default=None, description="元数据插件列表")
    subtitle_plugins: Optional[List[str]] = Field(default=None, description="字幕插件列表")


class GetLibrarySchema(BaseModel):
    """获取媒体库详情参数模型。"""

    library_id: str = Field(description="媒体库ID")


class UpdateLibrarySchema(BaseModel):
    """更新媒体库参数模型。"""

    library_id: str = Field(description="媒体库ID")
    name: Optional[str] = Field(default=None, description="媒体库名称")
    root_path: Optional[str] = Field(default=None, description="存储根路径")
    description: Optional[str] = Field(default=None, description="媒体库描述")
    scan_interval: Optional[int] = Field(default=None, description="自动扫描间隔（秒）")
    auto_import: Optional[bool] = Field(default=None, description="是否自动导入媒体")
    auto_import_scan_path: Optional[str] = Field(default=None, description="自动导入扫描路径")
    supported_formats: Optional[List[str]] = Field(default=None, description="支持的视频格式列表")
    activated_plugins: Optional[Dict[str, List[str]]] = Field(default=None, description="激活插件映射（类型 -> 插件名列表）")


class DeleteLibrarySchema(BaseModel):
    """删除媒体库参数模型。"""

    library_id: str = Field(description="媒体库ID")
    soft_delete: bool = Field(default=True, description="是否软删除")


class RestoreLibrarySchema(BaseModel):
    """恢复媒体库参数模型。"""

    library_id: str = Field(description="媒体库ID")


class ListLibrariesSchema(BaseModel):
    """查询媒体库列表参数模型。"""

    query: Optional[str] = Field(default=None, description="搜索关键词")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=1000, description="每页数量")
    library_type: Optional[str] = Field(default=None, description="媒体库类型，目前只支持 'movie' 或 'tv'")
    is_active: Optional[bool] = Field(default=None, description="是否启用")
    is_deleted: Optional[bool] = Field(default=None, description="是否已删除")
    auto_import: Optional[bool] = Field(default=None, description="是否自动导入")
    only_me: bool = Field(default=False, description="是否仅查询当前用户的媒体库")


class UpdateLibraryActivitySchema(BaseModel):
    """更新媒体库启用状态参数模型。"""

    library_id: str = Field(description="媒体库ID")
    is_active: bool = Field(description="是否启用")


class UpdateLibraryVisibilitySchema(BaseModel):
    """更新媒体库可见性参数模型。"""

    library_id: str = Field(description="媒体库ID")
    is_public: bool = Field(description="是否公开")


class GetLibraryStatsSchema(BaseModel):
    """获取媒体库统计信息参数模型。"""

    library_id: str = Field(description="媒体库ID")


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


def _get_library_service() -> Any:
    """获取 LibraryService 实例。"""
    from src.services.movies.library_service import LibraryService

    return LibraryService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def create_library_tool(
    name: str,
    type: str,
    description: str,
    is_public: bool,
    metadata_plugins: Optional[List[str]],
    subtitle_plugins: Optional[List[str]],
    ctx: Optional[RequestContext] = None,
) -> str:
    """创建一个新的媒体库。仅限非访客用户操作。"""
    validated = _validate_schema(
        CreateLibrarySchema,
        name=name,
        type=type,
        description=description,
        is_public=is_public,
        metadata_plugins=metadata_plugins,
        subtitle_plugins=subtitle_plugins,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        # 使用统一的构造函数，确保与HTTP路由逻辑完全一致
        from .builders import build_library_create_payload
        data = build_library_create_payload(
            name=name,
            library_type=type,
            description=description,
            is_public=is_public,
            metadata_plugins=metadata_plugins,
            subtitle_plugins=subtitle_plugins,
            user_id=current_user.id,
        )
        result = await service.create_library(data, current_user=current_user)
        return f"媒体库创建成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


async def get_library_tool(
    library_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取媒体库详情。"""
    if not library_id:
        return "参数验证失败: library_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_library(library_id, current_user=current_user)
        return f"媒体库详情: {result.model_dump_json()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def update_library_tool(
    library_id: str,
    name: Optional[str],
    root_path: Optional[str],
    description: Optional[str],
    scan_interval: Optional[int],
    auto_import: Optional[bool],
    auto_import_scan_path: Optional[str],
    supported_formats: Optional[List[str]],
    activated_plugins: Optional[Dict[str, List[str]]],
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新媒体库信息。"""
    validated = _validate_schema(
        UpdateLibrarySchema,
        library_id=library_id,
        name=name,
        root_path=root_path,
        description=description,
        scan_interval=scan_interval,
        auto_import=auto_import,
        auto_import_scan_path=auto_import_scan_path,
        supported_formats=supported_formats,
        activated_plugins=activated_plugins,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        patch_payload = {
            "name": validated.name,
            "root_path": validated.root_path,
            "description": validated.description,
            "scan_interval": validated.scan_interval,
            "auto_import": validated.auto_import,
            "auto_import_scan_path": validated.auto_import_scan_path,
            "supported_formats": validated.supported_formats,
            "activated_plugins": validated.activated_plugins,
        }
        patch = LibraryUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        result = await service.update_library(validated.library_id, patch, current_user=current_user)
        return f"媒体库更新成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def delete_library_tool(
    library_id: str,
    soft_delete: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """删除媒体库。"""
    validated = _validate_schema(DeleteLibrarySchema, library_id=library_id, soft_delete=soft_delete)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        deleted_model, task_ctx = await service.delete_library(
            validated.library_id, soft_delete=validated.soft_delete, current_user=current_user
        )
        if task_ctx:
            return f"删除成功: {deleted_model.name}，任务: {task_ctx}"
        return f"删除成功: {deleted_model.name}"
    except Exception as e:
        return f"删除失败: {str(e)}"


async def restore_library_tool(
    library_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """恢复媒体库。"""
    validated = _validate_schema(RestoreLibrarySchema, library_id=library_id)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.restore_library(validated.library_id, current_user=current_user)
        return f"媒体库恢复成功: {result.model_dump_json()}"
    except Exception as e:
        return f"恢复失败: {str(e)}"


async def list_libraries_tool(
    query: Optional[str],
    page: int,
    page_size: int,
    library_type: Optional[str],
    is_active: Optional[bool],
    is_deleted: Optional[bool],
    auto_import: Optional[bool],
    only_me: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """查询媒体库列表。单次查询最多支持返回 1000 条记录。"""
    validated = _validate_schema(
        ListLibrariesSchema,
        query=query,
        page=page,
        page_size=page_size,
        library_type=library_type,
        is_active=is_active,
        is_deleted=is_deleted,
        auto_import=auto_import,
        only_me=only_me,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import LibraryType

        library_type_value = LibraryType(validated.library_type) if validated.library_type else None
        result = await service.list_libraries(
            current_user=current_user,
            query=validated.query,
            page=validated.page,
            page_size=validated.page_size,
            library_type=library_type_value,
            is_active=validated.is_active,
            is_deleted=validated.is_deleted,
            auto_import=validated.auto_import,
            only_me=validated.only_me,
        )
        return f"媒体库列表: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def update_library_activity_tool(
    library_id: str,
    is_active: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新媒体库启用状态。"""
    validated = _validate_schema(UpdateLibraryActivitySchema, library_id=library_id, is_active=is_active)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.update_library_activity(
            validated.library_id, validated.is_active, current_user=current_user
        )
        return f"媒体库状态更新成功: {result.model_dump_json()}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def update_library_visibility_tool(
    library_id: str,
    is_public: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新媒体库可见性。"""
    validated = _validate_schema(UpdateLibraryVisibilitySchema, library_id=library_id, is_public=is_public)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.update_library_visibility(
            validated.library_id, validated.is_public, current_user=current_user
        )
        return f"媒体库可见性更新成功: {result.model_dump_json()}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def get_library_stats_tool(
    library_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取媒体库统计信息。"""
    validated = _validate_schema(GetLibraryStatsSchema, library_id=library_id)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_library_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_library_stats(validated.library_id, current_user=current_user)
        return f"媒体库统计: {result}"
    except Exception as e:
        return f"获取失败: {str(e)}"


def register_library_tools(registry: ToolRegistry) -> None:
    """注册媒体库相关工具。"""
    registry.register(
        ToolDefinition(
            name="create_library",
            description="创建一个新的媒体库。仅限非访客用户操作。",
            parameters=_schema(CreateLibrarySchema),
            handler=create_library_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_library",
            description="获取媒体库详情。",
            parameters=_schema(GetLibrarySchema),
            handler=get_library_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_library",
            description="更新媒体库信息。",
            parameters=_schema(UpdateLibrarySchema),
            handler=update_library_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_library",
            description="删除媒体库。",
            parameters=_schema(DeleteLibrarySchema),
            handler=delete_library_tool,
            category="libraries",
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="restore_library",
            description="恢复媒体库。",
            parameters=_schema(RestoreLibrarySchema),
            handler=restore_library_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_libraries",
            description="查询媒体库列表。单次查询最多支持返回 1000 条记录。",
            parameters=_schema(ListLibrariesSchema),
            handler=list_libraries_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_library_activity",
            description="更新媒体库启用状态。",
            parameters=_schema(UpdateLibraryActivitySchema),
            handler=update_library_activity_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_library_visibility",
            description="更新媒体库可见性。",
            parameters=_schema(UpdateLibraryVisibilitySchema),
            handler=update_library_visibility_tool,
            category="libraries",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_library_stats",
            description="获取媒体库统计信息。",
            parameters=_schema(GetLibraryStatsSchema),
            handler=get_library_stats_tool,
            category="libraries",
        )
    )
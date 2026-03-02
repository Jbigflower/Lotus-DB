from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List, Dict, Any

from src.services.movies.library_service import LibraryService
from src.agent.tools.builders import build_library_create_payload

# 1. 定义工具参数的 Schema (有助于 LLM 理解复杂对象)
class CreateLibrarySchema(BaseModel):
    name: str = Field(description="媒体库名称")
    library_type: str = Field(description="媒体库类型，目前只支持 'movie' 或 'tv'")
    description: str = Field(description="媒体库的详细描述")
    is_public: bool = Field(default=False, description="是否公开可见")
    metadata_plugins: Optional[List[str]] = Field(default=None, description="元数据插件列表")
    subtitle_plugins: Optional[List[str]] = Field(default=None, description="字幕插件列表")

class GetLibrarySchema(BaseModel):
    library_id: str = Field(description="媒体库ID")

class UpdateLibrarySchema(BaseModel):
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
    library_id: str = Field(description="媒体库ID")
    soft_delete: bool = Field(default=True, description="是否软删除")

class RestoreLibrarySchema(BaseModel):
    library_id: str = Field(description="媒体库ID")

class ListLibrariesSchema(BaseModel):
    query: Optional[str] = Field(default=None, description="搜索关键词")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=10, description="每页数量")
    library_type: Optional[str] = Field(default=None, description="媒体库类型，目前只支持 'movie' 或 'tv'")
    is_active: Optional[bool] = Field(default=None, description="是否启用")
    is_deleted: Optional[bool] = Field(default=None, description="是否已删除")
    auto_import: Optional[bool] = Field(default=None, description="是否自动导入")
    only_me: bool = Field(default=False, description="是否仅查询当前用户的媒体库")

class UpdateLibraryActivitySchema(BaseModel):
    library_id: str = Field(description="媒体库ID")
    is_active: bool = Field(description="是否启用")

class UpdateLibraryVisibilitySchema(BaseModel):
    library_id: str = Field(description="媒体库ID")
    is_public: bool = Field(description="是否公开")

class GetLibraryStatsSchema(BaseModel):
    library_id: str = Field(description="媒体库ID")

# 2. 封装：创建媒体库
@tool(args_schema=CreateLibrarySchema)
async def create_library_tool(
    name: str, 
    library_type: str,
    description: str,
    is_public: bool, 
    metadata_plugins: Optional[List[str]],
    subtitle_plugins: Optional[List[str]],
    runtime: ToolRuntime
) -> str:
    """创建一个新的媒体库。仅限非访客用户操作。"""
    
    # 从运行时上下文中获取 UserLogic 需要的 User 对象
    current_user = runtime.context.get("user") 
    service = LibraryService() # 建议使用单例或从 context 获取
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"

    try:
        # 使用统一的构造函数，复用HTTP路由的逻辑
        data = build_library_create_payload(
            name=name,
            library_type=library_type,
            description=description,
            is_public=is_public,
            metadata_plugins=metadata_plugins,
            subtitle_plugins=subtitle_plugins,
            user_id=current_user.id
        )
        
        result = await service.create_library(data, current_user=current_user)
        return f"媒体库创建成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"

@tool(args_schema=GetLibrarySchema)
async def get_library_tool(
    library_id: str,
    runtime: ToolRuntime
) -> str:
    """获取媒体库详情。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_library(library_id, current_user=current_user)
        return f"媒体库详情: {result.model_dump_json()}"
    except Exception as e:
        return f"获取失败: {str(e)}"

@tool(args_schema=UpdateLibrarySchema)
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
    runtime: ToolRuntime
) -> str:
    """更新媒体库信息。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import LibraryUpdate
        payload = {
            "name": name,
            "root_path": root_path,
            "description": description,
            "scan_interval": scan_interval,
            "auto_import": auto_import,
            "auto_import_scan_path": auto_import_scan_path,
            "supported_formats": supported_formats,
            "activated_plugins": activated_plugins,
        }
        data = LibraryUpdate(**payload)
        result = await service.update_library(library_id, data, current_user=current_user)
        return f"媒体库更新成功: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"

@tool(args_schema=DeleteLibrarySchema)
async def delete_library_tool(
    library_id: str,
    soft_delete: bool,
    runtime: ToolRuntime
) -> str:
    """删除媒体库。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        deleted_model, task_ctx = await service.delete_library(
            library_id, soft_delete=soft_delete, current_user=current_user
        )
        if task_ctx:
            return f"删除成功: {deleted_model.name}，任务: {task_ctx}"
        return f"删除成功: {deleted_model.name}"
    except Exception as e:
        return f"删除失败: {str(e)}"

@tool(args_schema=RestoreLibrarySchema)
async def restore_library_tool(
    library_id: str,
    runtime: ToolRuntime
) -> str:
    """恢复媒体库。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.restore_library(library_id, current_user=current_user)
        return f"媒体库恢复成功: {result.model_dump_json()}"
    except Exception as e:
        return f"恢复失败: {str(e)}"

@tool(args_schema=ListLibrariesSchema)
async def list_libraries_tool(
    query: Optional[str],
    page: int,
    page_size: int,
    library_type: Optional[str],
    is_active: Optional[bool],
    is_deleted: Optional[bool],
    auto_import: Optional[bool],
    only_me: bool,
    runtime: ToolRuntime
) -> str:
    """查询媒体库列表。单次查询最多支持返回 1000 条记录。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import LibraryType
        library_type_value = LibraryType(library_type) if library_type else None
        result = await service.list_libraries(
            current_user=current_user,
            query=query,
            page=page,
            page_size=page_size,
            library_type=library_type_value,
            is_active=is_active,
            is_deleted=is_deleted,
            auto_import=auto_import,
            only_me=only_me,
        )
        return f"媒体库列表: {result.model_dump_json()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"查询失败: {str(e)}"

@tool(args_schema=UpdateLibraryActivitySchema)
async def update_library_activity_tool(
    library_id: str,
    is_active: bool,
    runtime: ToolRuntime
) -> str:
    """更新媒体库启用状态。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.update_library_activity(
            library_id, is_active, current_user=current_user
        )
        return f"媒体库状态更新成功: {result.model_dump_json()}"
    except Exception as e:
        return f"更新失败: {str(e)}"

@tool(args_schema=UpdateLibraryVisibilitySchema)
async def update_library_visibility_tool(
    library_id: str,
    is_public: bool,
    runtime: ToolRuntime
) -> str:
    """更新媒体库可见性。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.update_library_visibility(
            library_id, is_public, current_user=current_user
        )
        return f"媒体库可见性更新成功: {result.model_dump_json()}"
    except Exception as e:
        return f"更新失败: {str(e)}"

@tool(args_schema=GetLibraryStatsSchema)
async def get_library_stats_tool(
    library_id: str,
    runtime: ToolRuntime
) -> str:
    """获取媒体库统计信息。"""
    current_user = runtime.context.get("user")
    service = LibraryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_library_stats(library_id, current_user=current_user)
        return f"媒体库统计: {result}"
    except Exception as e:
        return f"获取失败: {str(e)}"
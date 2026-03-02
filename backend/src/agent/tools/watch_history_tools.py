from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
from src.services.users.watch_history_service import WatchHistoryService
from src.agent.tools.builders import build_watch_history_create_payload


class ListUserWatchHistoriesSchema(BaseModel):
    watch_type: Optional[str] = Field(default=None, description="观看类型 Official|Community")
    completed: Optional[bool] = Field(default=None, description="是否完成观看")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")


class GetWatchHistorySchema(BaseModel):
    watch_history_id: str = Field(description="观看历史ID")


class CreateWatchHistorySchema(BaseModel):
    asset_id: str = Field(description="资产ID")
    movie_id: Optional[str] = Field(default=None, description="电影ID")
    type: str = Field(description="观看类型 Official|Community")
    last_position: int = Field(default=0, description="最后观看位置（秒）")
    total_duration: int = Field(default=0, description="媒体总时长（秒）")
    subtitle_enabled: bool = Field(default=False, description="是否启用字幕")
    subtitle_id: Optional[str] = Field(default=None, description="字幕ID")
    subtitle_sync_data: Optional[int] = Field(default=None, description="字幕同步（秒）")
    playback_rate: float = Field(default=1.0, description="播放倍速")


class UpdateWatchHistorySchema(BaseModel):
    watch_history_id: str = Field(description="观看历史ID")
    last_position: Optional[int] = Field(default=None, description="最后观看位置（秒）")
    total_duration: Optional[int] = Field(default=None, description="媒体总时长（秒）")
    total_watch_time: Optional[int] = Field(default=None, description="总观看时长（秒）")
    watch_count: Optional[int] = Field(default=None, description="观看次数")
    subtitle_enabled: Optional[bool] = Field(default=None, description="是否启用字幕")
    subtitle_id: Optional[str] = Field(default=None, description="字幕ID")
    subtitle_sync_data: Optional[int] = Field(default=None, description="字幕同步（秒）")
    playback_rate: Optional[float] = Field(default=None, description="播放倍速")


class DeleteWatchHistoriesSchema(BaseModel):
    watch_history_ids: List[str] = Field(description="观看历史ID列表")


class GetRecentWatchHistoriesSchema(BaseModel):
    limit: Optional[int] = Field(default=None, description="返回数量上限")


class GetWatchStatisticsSchema(BaseModel):
    pass


class ListUserAssetWatchHistoriesSchema(BaseModel):
    asset_id: str = Field(description="资产ID")
    asset_type: str = Field(description="资产类型 Official|Community")


@tool(args_schema=ListUserWatchHistoriesSchema)
async def list_user_watch_histories_tool(
    watch_type: Optional[str],
    completed: Optional[bool],
    page: int,
    size: int,
    runtime: ToolRuntime,
) -> str:
    """列出我的观看历史，支持类型、完成状态筛选与分页。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import WatchType
        wt = WatchType(watch_type) if watch_type else None
        result = await service.list_user_watch_histories(current_user, wt, completed, page, size)
        return f"观看历史列表: {result.model_dump()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=GetWatchHistorySchema)
async def get_watch_history_by_id_tool(
    watch_history_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取单条观看历史详情。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        read = await service.get_watch_history_by_id(watch_history_id, current_user)
        return f"观看历史详情: {read.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=CreateWatchHistorySchema)
async def create_watch_history_tool(
    asset_id: str,
    movie_id: Optional[str],
    type: str,
    last_position: int,
    total_duration: int,
    subtitle_enabled: bool,
    subtitle_id: Optional[str],
    subtitle_sync_data: Optional[int],
    playback_rate: float,
    runtime: ToolRuntime,
) -> str:
    """创建观看历史记录。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        # 使用统一的构造函数，复用HTTP路由的逻辑
        payload = build_watch_history_create_payload(
            asset_id=asset_id,
            movie_id=movie_id,
            type=type,
            last_position=last_position,
            total_duration=total_duration,
            subtitle_enabled=subtitle_enabled,
            subtitle_id=subtitle_id,
            subtitle_sync_data=subtitle_sync_data,
            playback_rate=playback_rate,
            user_id=current_user.id
        )
        created = await service.create_watch_history(payload, current_user)
        return f"观看历史创建成功: {created.id}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


@tool(args_schema=UpdateWatchHistorySchema)
async def update_watch_history_by_id_tool(
    watch_history_id: str,
    last_position: Optional[int],
    total_duration: Optional[int],
    total_watch_time: Optional[int],
    watch_count: Optional[int],
    subtitle_enabled: Optional[bool],
    subtitle_id: Optional[str],
    subtitle_sync_data: Optional[int],
    playback_rate: Optional[float],
    runtime: ToolRuntime,
) -> str:
    """更新观看历史的进度、统计与字幕设置。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import WatchHistoryUpdate
        patch = WatchHistoryUpdate(
            last_position=last_position,
            total_duration=total_duration,
            total_watch_time=total_watch_time,
            watch_count=watch_count,
            subtitle_enabled=subtitle_enabled,
            subtitle_id=subtitle_id,
            subtitle_sync_data=subtitle_sync_data,
            playback_rate=playback_rate,
        )
        updated = await service.update_watch_history_by_id(watch_history_id, patch, current_user)
        return f"观看历史更新成功: {updated.model_dump()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


@tool(args_schema=DeleteWatchHistoriesSchema)
async def delete_watch_histories_tool(
    watch_history_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """批量删除观看历史。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        count = await service.delete_watch_histories(watch_history_ids, current_user)
        return f"删除成功: {count} 条记录"
    except Exception as e:
        return f"删除失败: {str(e)}"


@tool(args_schema=GetRecentWatchHistoriesSchema)
async def get_recent_watch_histories_tool(
    limit: Optional[int],
    runtime: ToolRuntime,
) -> str:
    """获取最近的观看记录。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        items = await service.get_recent_watch_histories(current_user, limit)
        return f"最近观看记录: {[i.model_dump() for i in items]}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=GetWatchStatisticsSchema)
async def get_watch_statistics_tool(
    runtime: ToolRuntime,
) -> str:
    """获取我的观看统计数据。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        stat = await service.get_watch_statistics(current_user)
        return f"观看统计: {stat}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=ListUserAssetWatchHistoriesSchema)
async def list_user_asset_watch_histories_tool(
    asset_id: str,
    asset_type: str,
    runtime: ToolRuntime,
) -> str:
    """列出某资产的观看历史。"""
    current_user = runtime.context.get("user")
    service = WatchHistoryService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import WatchType
        read = await service.list_user_asset_watch_histories(asset_id, WatchType(asset_type), current_user)
        return f"资产观看历史: {read.model_dump() if read else None}"
    except Exception as e:
        return f"查询失败: {str(e)}"

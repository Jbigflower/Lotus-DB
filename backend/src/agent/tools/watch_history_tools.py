from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import WatchHistoryCreate, WatchHistoryUpdate, UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class ListUserWatchHistoriesSchema(BaseModel):
    """查询用户观看历史列表参数模型。"""

    watch_type: Optional[str] = Field(default=None, description="观看类型 Official|Community")
    completed: Optional[bool] = Field(default=None, description="是否完成观看")
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")


class GetWatchHistorySchema(BaseModel):
    """获取观看历史详情参数模型。"""

    watch_history_id: str = Field(description="观看历史ID")


class CreateWatchHistorySchema(BaseModel):
    """创建观看历史参数模型。"""

    asset_id: str = Field(description="资产ID")
    movie_id: Optional[str] = Field(default=None, description="电影ID")
    type: str = Field(description="观看类型 Official|Community")
    last_position: int = Field(default=0, ge=0, description="最后观看位置（秒）")
    total_duration: int = Field(default=0, ge=0, description="媒体总时长（秒）")
    subtitle_enabled: bool = Field(default=False, description="是否启用字幕")
    subtitle_id: Optional[str] = Field(default=None, description="字幕ID")
    subtitle_sync_data: Optional[int] = Field(default=None, description="字幕同步（秒）")
    playback_rate: float = Field(default=1.0, ge=0.1, le=4.0, description="播放倍速")


class UpdateWatchHistorySchema(BaseModel):
    """更新观看历史参数模型。"""

    watch_history_id: str = Field(description="观看历史ID")
    last_position: Optional[int] = Field(default=None, ge=0, description="最后观看位置（秒）")
    total_duration: Optional[int] = Field(default=None, ge=0, description="媒体总时长（秒）")
    total_watch_time: Optional[int] = Field(default=None, ge=0, description="总观看时长（秒）")
    watch_count: Optional[int] = Field(default=None, ge=0, description="观看次数")
    subtitle_enabled: Optional[bool] = Field(default=None, description="是否启用字幕")
    subtitle_id: Optional[str] = Field(default=None, description="字幕ID")
    subtitle_sync_data: Optional[int] = Field(default=None, description="字幕同步（秒）")
    playback_rate: Optional[float] = Field(default=None, ge=0.1, le=4.0, description="播放倍速")


class DeleteWatchHistoriesSchema(BaseModel):
    """删除观看历史参数模型。"""

    watch_history_ids: List[str] = Field(description="观看历史ID列表")


class GetRecentWatchHistoriesSchema(BaseModel):
    """获取最近观看历史参数模型。"""

    limit: Optional[int] = Field(default=None, ge=1, le=100, description="返回数量上限")


class GetWatchStatisticsSchema(BaseModel):
    """获取观看统计数据参数模型。"""

    pass


class ListUserAssetWatchHistoriesSchema(BaseModel):
    """查询用户资产观看历史参数模型。"""

    asset_id: str = Field(description="资产ID")
    asset_type: str = Field(description="资产类型 Official|Community")


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


def _get_watch_history_service() -> Any:
    """获取 WatchHistoryService 实例。"""
    from src.services.users.watch_history_service import WatchHistoryService

    return WatchHistoryService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def list_user_watch_histories_tool(
    watch_type: Optional[str],
    completed: Optional[bool],
    page: int,
    size: int,
    ctx: Optional[RequestContext] = None,
) -> str:
    """列出我的观看历史，支持类型、完成状态筛选与分页。"""
    validated = _validate_schema(
        ListUserWatchHistoriesSchema,
        watch_type=watch_type,
        completed=completed,
        page=page,
        size=size,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import WatchType

        wt = WatchType(validated.watch_type) if validated.watch_type else None
        result = await service.list_user_watch_histories(current_user, wt, validated.completed, validated.page, validated.size)
        return f"观看历史列表: {result.model_dump()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def get_watch_history_by_id_tool(
    watch_history_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取单条观看历史详情。"""
    if not watch_history_id:
        return "参数验证失败: watch_history_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        read = await service.get_watch_history_by_id(validated.watch_history_id, current_user)
        return f"观看历史详情: {read.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


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
    ctx: Optional[RequestContext] = None,
) -> str:
    """创建观看历史记录。"""
    validated = _validate_schema(
        CreateWatchHistorySchema,
        asset_id=asset_id,
        movie_id=movie_id,
        type=type,
        last_position=last_position,
        total_duration=total_duration,
        subtitle_enabled=subtitle_enabled,
        subtitle_id=subtitle_id,
        subtitle_sync_data=subtitle_sync_data,
        playback_rate=playback_rate,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.agent.tools.builders import build_watch_history_create_payload

        payload = build_watch_history_create_payload(
            asset_id=validated.asset_id,
            movie_id=validated.movie_id,
            type=validated.type,
            last_position=validated.last_position,
            total_duration=validated.total_duration,
            subtitle_enabled=validated.subtitle_enabled,
            subtitle_id=validated.subtitle_id,
            subtitle_sync_data=validated.subtitle_sync_data,
            playback_rate=validated.playback_rate,
            user_id=current_user.id,
        )
        created = await service.create_watch_history(payload, current_user)
        return f"观看历史创建成功: {created.id}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


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
    ctx: Optional[RequestContext] = None,
) -> str:
    """更新观看历史的进度、统计与字幕设置。"""
    validated = _validate_schema(
        UpdateWatchHistorySchema,
        watch_history_id=watch_history_id,
        last_position=last_position,
        total_duration=total_duration,
        total_watch_time=total_watch_time,
        watch_count=watch_count,
        subtitle_enabled=subtitle_enabled,
        subtitle_id=subtitle_id,
        subtitle_sync_data=subtitle_sync_data,
        playback_rate=playback_rate,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        patch_payload = {
            "last_position": validated.last_position,
            "total_duration": validated.total_duration,
            "total_watch_time": validated.total_watch_time,
            "watch_count": validated.watch_count,
            "subtitle_enabled": validated.subtitle_enabled,
            "subtitle_id": validated.subtitle_id,
            "subtitle_sync_data": validated.subtitle_sync_data,
            "playback_rate": validated.playback_rate,
        }
        patch = WatchHistoryUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        updated = await service.update_watch_history_by_id(validated.watch_history_id, patch, current_user)
        return f"观看历史更新成功: {updated.model_dump()}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def delete_watch_histories_tool(
    watch_history_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量删除观看历史。"""
    validated = _validate_schema(DeleteWatchHistoriesSchema, watch_history_ids=watch_history_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.watch_history_ids:
        return "参数验证失败: 观看历史ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        count = await service.delete_watch_histories(validated.watch_history_ids, current_user)
        return f"删除成功: {count} 条记录"
    except Exception as e:
        return f"删除失败: {str(e)}"


async def get_recent_watch_histories_tool(
    limit: Optional[int],
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取最近的观看记录。"""
    validated = _validate_schema(GetRecentWatchHistoriesSchema, limit=limit)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        items = await service.get_recent_watch_histories(current_user, validated.limit)
        return f"最近观看记录: {[i.model_dump() for i in items]}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def get_watch_statistics_tool(ctx: Optional[RequestContext] = None) -> str:
    """获取我的观看统计数据。"""
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        stat = await service.get_watch_statistics(current_user)
        return f"观看统计: {stat}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def list_user_asset_watch_histories_tool(
    asset_id: str,
    asset_type: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """列出某资产的观看历史。"""
    validated = _validate_schema(ListUserAssetWatchHistoriesSchema, asset_id=asset_id, asset_type=asset_type)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_watch_history_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import WatchType

        read = await service.list_user_asset_watch_histories(validated.asset_id, WatchType(validated.asset_type), current_user)
        return f"资产观看历史: {read.model_dump() if read else None}"
    except Exception as e:
        return f"查询失败: {str(e)}"


def register_watch_history_tools(registry: ToolRegistry) -> None:
    """注册观看历史相关工具。"""
    registry.register(
        ToolDefinition(
            name="list_user_watch_histories",
            description="列出我的观看历史，支持类型、完成状态筛选与分页。",
            parameters=_schema(ListUserWatchHistoriesSchema),
            handler=list_user_watch_histories_tool,
            category="watch_history",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_watch_history_by_id",
            description="获取单条观看历史详情。",
            parameters=_schema(GetWatchHistorySchema),
            handler=get_watch_history_by_id_tool,
            category="watch_history",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_watch_history",
            description="创建观看历史记录。",
            parameters=_schema(CreateWatchHistorySchema),
            handler=create_watch_history_tool,
            category="watch_history",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_watch_history_by_id",
            description="更新观看历史的进度、统计与字幕设置。",
            parameters=_schema(UpdateWatchHistorySchema),
            handler=update_watch_history_by_id_tool,
            category="watch_history",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_watch_histories",
            description="批量删除观看历史。",
            parameters=_schema(DeleteWatchHistoriesSchema),
            handler=delete_watch_histories_tool,
            category="watch_history",
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_recent_watch_histories",
            description="获取最近的观看记录。",
            parameters=_schema(GetRecentWatchHistoriesSchema),
            handler=get_recent_watch_histories_tool,
            category="watch_history",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_watch_statistics",
            description="获取我的观看统计数据。",
            parameters=_schema(GetWatchStatisticsSchema),
            handler=get_watch_statistics_tool,
            category="watch_history",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_user_asset_watch_histories",
            description="列出某资产的观看历史。",
            parameters=_schema(ListUserAssetWatchHistoriesSchema),
            handler=list_user_asset_watch_histories_tool,
            category="watch_history",
        )
    )

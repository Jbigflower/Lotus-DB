from typing import List, Optional, Union, Dict
from pydantic import BaseModel, Field
from src.models import (
    WatchHistoryCreate,
    WatchHistoryUpdate,
    WatchHistoryRead,
    WatchHistoryPageResult,
    WatchType,
)


class WatchHistoryCreateRequestSchema(WatchHistoryCreate):
    """创建观看历史请求模型"""

    user_id: Optional[str] = Field(None, description="用户ID，后端依赖注入获取")


class WatchHistoryUpdateRequestSchema(WatchHistoryUpdate):
    """更新观看历史请求模型"""

    id: Optional[str] = Field(None, description="观看历史ID（PATCH 路由走路径参数；beacon 上报需携带）")


class WatchHistoryReadResponseSchema(WatchHistoryRead):
    """读取观看历史响应模型"""

    pass  # 所有字段从 WatchHistoryRead 继承，Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return WatchHistoryRead


class WatchHistoryPageResultResponseSchema(WatchHistoryPageResult):
    """观看历史分页结果响应模型"""

    pass


class WatchProgressUpdateSchema(BaseModel):
    """更新观看进度请求模型"""

    movie_id: str = Field(..., description="电影ID（Official 类型时必填）")
    asset_id: Optional[str] = Field(None, description="资产ID（播放的视频文件）")
    type: WatchType = Field(..., description="观看类型")
    last_position: int = Field(..., ge=0, description="最后观看位置（秒）")
    total_duration: Optional[int] = Field(None, ge=0, description="媒体总时长（秒）")
    device_info: Optional[Dict[str, str]] = Field(None, description="设备信息")
    subtitle_enabled: Optional[bool] = Field(None, description="是否启用字幕")
    subtitle_id: Optional[str] = Field(None, description="字幕ID")
    subtitle_sync_data: Optional[int] = Field(None, description="字幕同步信息（秒）")
    playback_rate: Optional[float] = Field(None, description="播放倍速")


class WatchStatisticsResponseSchema(BaseModel):
    """观看统计响应模型"""

    total_movies: int = Field(..., description="总观看影片数")
    total_watch_time: int = Field(..., description="总观看时长（秒）")
    total_watch_count: int = Field(..., description="总观看次数")
    avg_progress: float = Field(..., description="平均观看进度百分比")


class DeleteResultResponseSchema(BaseModel):
    """删除结果响应模型"""

    deleted: int = Field(..., description="删除的记录数")
    message: str = Field(..., description="删除结果消息")
    ok: bool = Field(..., description="是否删除成功")

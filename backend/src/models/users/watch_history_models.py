# src/models/watch_history_models.py
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


# -----------------------------
# 枚举类型
# -----------------------------
class WatchType(str, Enum):
    """观看类型，区分官方资产和社区资产"""

    Official = "Official"
    Community = "Community"


# -----------------------------
# Base 模型
# -----------------------------
class WatchHistoryBase(BaseModel):
    user_id: str = Field(..., description="用户ID")
    asset_id: str = Field(..., description="资产ID（具体播放的视频文件）")
    movie_id: Optional[str] = Field(None, description="电影ID（Official 类型时必填）")
    type: WatchType = Field(..., description="观看类型（Official/Community）")

    last_position: int = Field(0, description="最后观看位置（秒）")
    total_duration: int = Field(0, description="媒体总时长（秒）")
    subtitle_enabled: bool = Field(False, description="是否启用字幕")
    subtitle_id: Optional[str] = Field(None, description="字幕ID")
    subtitle_sync_data: Optional[int] = Field(None, description="字幕同步信息（秒）")
    playback_rate: float = Field(1.0, description="播放倍速")
    last_watched: Optional[datetime] = Field(None, description="最后观看时间")
    watch_count: int = Field(1, description="观看次数")
    total_watch_time: int = Field(0, description="总观看时长（秒）")
    device_info: Dict[str, str] = Field(default_factory=dict, description="设备信息")

    # class Config:
    #     orm_mode = True

    @property
    def progress_percentage(self) -> float:
        """动态计算观看百分比"""
        return (
            (self.last_position / self.total_duration * 100)
            if self.total_duration
            else 0.0
        )


# -----------------------------
# 创建模型
# -----------------------------
class WatchHistoryCreate(WatchHistoryBase):
    """创建观看历史"""

    pass


# -----------------------------
# 更新模型
# -----------------------------
class WatchHistoryUpdate(BaseModel):
    """更新观看历史"""

    last_position: Optional[int] = None
    total_duration: Optional[int] = Field(None, description="媒体总时长（秒）")
    total_watch_time: Optional[int] = None
    last_watched: Optional[datetime] = None
    watch_count: Optional[int] = None
    subtitle_enabled: Optional[bool] = None
    subtitle_id: Optional[str] = None
    subtitle_sync_data: Optional[int] = Field(None, description="字幕同步信息（秒）")
    playback_rate: Optional[float] = Field(None, description="播放倍速")
    device_info: Optional[Dict[str, str]] = None


# -----------------------------
# 数据库模型
# -----------------------------
class WatchHistoryInDB(WatchHistoryBase):
    id: str = Field(..., description="观看历史ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


# -----------------------------
# 读取模型
# -----------------------------
class WatchHistoryRead(WatchHistoryInDB):
    pass


# -----------------------------
# 分页结果
# -----------------------------
class WatchHistoryPageResult(BaseModel):
    items: List[WatchHistoryRead | WatchHistoryInDB] = Field(
        default_factory=list, description="观看历史列表"
    )
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum

# 通用常量定义
DEFAULT_VIDEO_FORMATS = ["mp4", "mkv", "avi", "mov", "srt", "jpg", "png", "jpeg"]


class LibraryType(str, Enum):
    """媒体库类型枚举"""

    MOVIE = "movie"  # 特点：电影资产内容相同，只是分辨率、码率等不同
    TV = "tv"  # 特点：电影资产内容不同，需要额外的编号对应具体的集数


# 2025.10.22 移至.env 作为部署层面的配置
# class LibraryStructure(BaseModel):
#     """媒体库文件结构模板"""
#     movie: str = Field("{movie_id}/", description="电影文件存储路径模板")
#     poster: str = Field("{movie_id}/poster.jpg", description="海报文件路径模板")
#     backdrop: str = Field("{movie_id}/backdrop.jpg", description="背景图文件路径模板")
#     thumbnail: str = Field("{movie_id}/thumbs/", description="缩略图文件夹路径模板")
#     subtitles: str = Field("{movie_id}/subs/", description="字幕文件存储路径模板")
#     video: str = Field("{movie_id}/video/", description="视频文件路径模板")


# 媒体库模型
class LibraryBase(BaseModel):
    """媒体库基础字段"""

    name: str = Field(..., min_length=1, max_length=100, description="媒体库名称")
    root_path: str = Field(..., description="存储根路径")
    type: LibraryType = Field(..., description="媒体库类型")
    # structure: LibraryStructure = Field(default_factory=LibraryStructure, description="文件结构模板配置")
    description: str = Field("", description="媒体库描述")
    scan_interval: int = Field(3600, ge=60, description="自动扫描间隔（秒）")
    auto_import: bool = Field(False, description="是否自动导入媒体")
    auto_import_scan_path: Optional[str] = Field(None, description="自动导入扫描路径")
    auto_import_supported_formats: Optional[List[str]] = Field(
        None, description="支持的视频格式列表"
    )
    # 新增：激活插件映射（类型 -> 插件名列表）
    activated_plugins: dict[str, List[str]] = Field(
        default_factory=lambda: {"metadata": [], "subtitle": []},
        description="激活插件映射：类型 -> 插件名列表（如 metadata/subtitle）",
    )

    is_public: bool = Field(False, description="是否公开访问")
    is_active: bool = Field(True, description="是否启用")


class LibraryCreate(LibraryBase):
    """创建媒体库请求模型"""

    user_id: str = Field(..., description="所属用户ID")
    root_path: Optional[str] = Field(None, description="存储根路径")


class LibraryUpdate(BaseModel):
    """更新媒体库请求模型"""

    name: Optional[str] = Field(None, description="媒体库名称")
    root_path: Optional[str] = Field(
        None, description="存储根路径"
    )  # 2025.10.22 用 用户ID + 媒体库名称 作为 root_path
    # structure: Optional[LibraryStructure] = Field(None, description="文件结构模板配置")
    description: Optional[str] = Field(None, description="媒体库描述")
    scan_interval: Optional[int] = Field(None, ge=60, description="自动扫描间隔（秒）")
    auto_import: Optional[bool] = Field(None, description="是否自动导入媒体")
    auto_import_scan_path: Optional[str] = Field(None, description="自动导入扫描路径")
    supported_formats: Optional[List[str]] = Field(
        None, description="支持的视频格式列表"
    )
    # 新增：允许更新激活插件映射
    activated_plugins: Optional[dict[str, List[str]]] = Field(
        None, description="更新激活插件映射（类型 -> 插件名列表）"
    )


class LibraryInDB(LibraryBase):
    """数据库中的媒体库模型"""

    id: str = Field(..., description="媒体库ID")
    user_id: str = Field(..., description="所属用户ID")
    is_deleted: bool = Field(False, description="软删除标记")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="创建时间（UTC）",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="更新时间（UTC）",
    )


class LibraryRead(LibraryInDB):
    """读取媒体库响应模型"""

    pass


class LibraryPageResult(BaseModel):
    """媒体库分页结果模型"""

    items: List[LibraryRead | LibraryInDB] = Field(default_factory=list, description="媒体库列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

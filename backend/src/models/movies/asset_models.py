"""
资产模型 - 多源资源、衍生资源、版本管理
支持视频、字幕、图片等独立管理，跨影片/跨库共享
"""

from datetime import datetime, timezone
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum


class AssetType(str, Enum):
    """资产类型枚举"""

    VIDEO = "video"
    SUBTITLE = "subtitle"
    IMAGE = "image"


class AssetStoreType(str, Enum):
    """资产存储类型枚举"""

    LOCAL = "local"
    S3 = "s3"


class VideoMetadata(BaseModel):
    """电影元数据子模型"""

    type: AssetType = Field(AssetType.VIDEO, description="资产类型")
    size: int = Field(0, ge=0, description="文件大小（字节）")
    duration: Optional[int] = Field(None, ge=0, description="时长（秒）")
    quality: Optional[str] = Field(None, description="质量标识")
    codec: Optional[str] = Field(None, description="编码格式")
    has_thumbnail: Optional[bool] = Field(None, description="是否有缩略图")
    has_sprite: Optional[bool] = Field(None, description="是否有雪碧图")
    width: Optional[int] = Field(None, ge=0, description="宽度（像素）")
    height: Optional[int] = Field(None, ge=0, description="高度（像素）")


class SubtitleMetadata(BaseModel):
    """字幕元数据子模型"""

    type: AssetType = Field(AssetType.SUBTITLE, description="资产类型")
    size: int = Field(0, ge=0, description="文件大小（字节）")
    language: Optional[str] = Field(None, description="字幕语言")


class ImageMetadata(BaseModel):
    """图片元数据子模型"""

    type: AssetType = Field(AssetType.IMAGE, description="资产类型")
    size: int = Field(0, ge=0, description="文件大小（字节）")
    width: Optional[int] = Field(None, ge=0, description="宽度（像素）")
    height: Optional[int] = Field(None, ge=0, description="高度（像素）")


class AssetBase(BaseModel):
    """资产基础字段"""

    library_id: str = Field(..., description="所属库ID")
    movie_id: str = Field(..., description="所属电影ID")
    type: AssetType = Field(..., description="资产类型")
    name: str = Field(..., min_length=1, description="资产名称")  # 播放时显示
    path: str = Field(..., min_length=1, description="文件路径")
    store_type: AssetStoreType = Field(..., description="资产存储类型")
    actual_path: Optional[str] = Field(None, description="实际存储路径")
    description: str = Field("", description="资产描述")
    tags: List[str] = Field(default_factory=list, description="标签")


class AssetCreate(AssetBase):
    """创建资产请求模型"""

    pass  # 所有字段从 AssetBase 继承


class AssetUpdate(BaseModel):
    """更新资产请求模型"""

    name: Optional[str] = Field(None, description="资产名称")
    description: Optional[str] = Field(None, description="资产描述")
    actual_path: Optional[str] = Field(None, description="实际存储路径")
    tags: Optional[List[str]] = Field(None, description="标签")
    metadata: Optional[Union[VideoMetadata, SubtitleMetadata, ImageMetadata]] = Field(
        None, description="资产元数据"
    )


class AssetInDB(AssetBase):
    """数据库中的资产模型"""

    id: str = Field(..., description="资产ID")
    metadata: Optional[Union[VideoMetadata, SubtitleMetadata, ImageMetadata]] = Field(
        None, description="资产元数据"
    )
    is_deleted: bool = Field(False, description="软删除标记")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    created_at: datetime = Field(None, description="创建时间")
    updated_at: datetime = Field(None, description="更新时间")


class AssetRead(AssetInDB):
    """读取资产响应模型"""

    pass


class AssetPageResult(BaseModel):
    """资产分页结果模型"""

    items: List[AssetRead | AssetInDB] = Field(default_factory=list, description="资产列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

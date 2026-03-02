"""
用户个人创作内容模型
支持笔记、截图、剪辑、影评等用户生成内容，每个资产对应单部电影和单版本
"""

from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum


# -------------------------------
# 枚举类型
# -------------------------------
class UserAssetType(str, Enum):
    """用户资产类型枚举"""

    NOTE = "note"
    SCREENSHOT = "screenshot"
    CLIP = "clip"
    REVIEW = "review"


class AssetStoreType(str, Enum):
    """资产存储类型枚举"""

    LOCAL = "local"
    S3 = "s3"


class ClipMetadata(BaseModel):
    """剪辑元数据子模型"""

    type: UserAssetType = Field(UserAssetType.CLIP, description="资产类型")
    size: Optional[int] = Field(None, ge=0, description="文件大小（字节）")
    duration: Optional[int] = Field(None, ge=0, description="时长（秒）")
    quality: Optional[str] = Field(None, description="质量标识")
    codec: Optional[str] = Field(None, description="编码格式")
    width: Optional[int] = Field(None, description="视频宽度")
    height: Optional[int] = Field(None, description="视频高度")
    has_thumbnail: Optional[bool] = Field(None, description="是否有缩略图")
    has_sprite: Optional[bool] = Field(None, description="是否有雪碧图")


class ScreenShotMetadata(BaseModel):
    """截图元数据子模型"""

    type: UserAssetType = Field(UserAssetType.SCREENSHOT, description="资产类型")
    size: Optional[int] = Field(None, ge=0, description="文件大小（字节）")
    width: Optional[int] = Field(None, ge=0, description="宽度（像素）")
    height: Optional[int] = Field(None, ge=0, description="高度（像素）")


class UserAssetBase(BaseModel):
    """用户资产公共字段"""

    movie_id: str = Field(..., description="关联电影ID")
    type: UserAssetType = Field(..., description="资产类型")
    name: str = Field(..., min_length=1, max_length=200, description="名称")
    related_movie_ids: List[str] = Field(
        default_factory=list, description="关联的其他电影ID"
    )  # 默认[]
    tags: List[str] = Field(default_factory=list, description="标签")

    is_public: bool = Field(False, description="是否公开")
    permissions: List[str] = Field(default_factory=list, description="权限控制")

    path: str = Field(..., min_length=1, description="文件路径")
    store_type: AssetStoreType = Field(..., description="资产存储类型")
    actual_path: Optional[str] = Field(None, description="实际存储路径")
    content: Optional[str] = Field(None, description="文本内容")


class UserAssetCreate(UserAssetBase):
    """创建用户资产请求模型"""

    user_id: str = Field(..., description="所属用户ID")


class UserAssetUpdate(BaseModel):
    """更新用户资产请求模型"""

    name: str = Field(..., min_length=1, max_length=200, description="名称")
    related_movie_ids: Optional[List[str]] = Field(None, description="关联的其他电影ID")
    tags: Optional[List[str]] = Field(None, description="标签")
    content: Optional[str] = Field(None, description="文本内容")
    metadata: Optional[Union[ClipMetadata, ScreenShotMetadata]] = Field(
        None, description="资产元数据"
    )


class UserAssetInDB(UserAssetBase):
    """数据库公共字段"""

    id: str = Field(..., description="资产ID")
    user_id: str = Field(..., description="所属用户ID")
    metadata: Optional[Union[ClipMetadata, ScreenShotMetadata]] = Field(
        None, description="资产元数据"
    )
    is_deleted: bool = Field(False, description="软删除标记")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    movie_info: Optional[dict] = Field(
        None, description="电影信息快照"
    )  # 只有资产孤立时需要保留
    require_allocate: bool = False  # # 只有资产孤立时需分配


class UserAssetRead(UserAssetInDB):
    """读取用户资产响应模型"""

    pass


class UserAssetPageResult(BaseModel):
    """用户资产分页结果模型"""

    items: List[UserAssetRead | UserAssetInDB] = Field(default_factory=list, description="资产列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

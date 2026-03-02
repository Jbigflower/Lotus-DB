"""
电影核心元数据模型
包含高频访问字段聚合，前端展示只需一次查询
"""

from datetime import date, datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, field_serializer


class MovieMetadata(BaseModel):
    """电影元数据子模型"""

    duration: Optional[int] = Field(None, description="时长（秒）")
    country: List[str] = Field(default_factory=list, description="制片国家")
    language: Optional[str] = Field(None, description="主要语言")


class MovieBase(BaseModel):
    """电影基础字段"""

    library_id: str = Field(..., description="所属媒体库ID")
    title: str = Field(..., description="英文标题")
    title_cn: str = Field("", description="中文标题")
    directors: List[str] = Field(default_factory=list, description="导演列表")
    actors: List[str] = Field(default_factory=list, description="演员列表")
    description: str = Field("", description="英文描述")
    description_cn: str = Field("", description="中文描述")
    release_date: Optional[date] = Field(None, description="上映日期 YYYY-MM-DD")
    genres: List[str] = Field(default_factory=list, description="官方标签")
    metadata: MovieMetadata = Field(default_factory=MovieMetadata, description="元数据")
    rating: Optional[float] = Field(None, ge=0, le=10, description="评分")
    tags: List[str] = Field(default_factory=list, description="用户标签")


class MovieCreate(MovieBase):
    """创建电影请求模型"""

    pass  # 所有字段从 MovieBase 继承


class MovieUpdate(BaseModel):
    """更新电影请求模型"""

    title: Optional[str] = Field(None, description="英文标题")
    title_cn: Optional[str] = Field(None, description="中文标题")
    directors: Optional[List[str]] = Field(None, description="导演列表")
    actors: Optional[List[str]] = Field(None, description="演员列表")
    description: Optional[str] = Field(None, description="英文描述")
    description_cn: Optional[str] = Field(None, description="中文描述")
    release_date: Optional[date] = Field(None, description="上映日期 YYYY-MM-DD")
    genres: Optional[List[str]] = Field(None, description="官方标签")
    metadata: Optional[MovieMetadata] = Field(None, description="元数据")
    rating: Optional[float] = Field(None, ge=0, le=10, description="评分")
    tags: Optional[List[str]] = Field(None, description="用户标签")

    # 专门的函数处理
    # has_poster: Optional[bool] = Field(None, description="是否有海报")
    # has_backdrop: Optional[bool] = Field(None, description="是否有背景图")
    # has_thumbnail: Optional[bool] = Field(None, description="是否有缩略图")

    # 2025.10.23 去除关联字段；查询优势不明显且维护成本高
    # video_asset_ids: List[str] = Field(default_factory=list, description="视频资产ID列表")
    # subtitle_asset_ids: List[str] = Field(default_factory=list, description="字幕资产ID列表")


class MovieInDB(MovieBase):
    """数据库中的电影模型"""

    id: str = Field(..., description="电影ID")

    has_poster: bool = Field(False, description="是否有海报")
    has_backdrop: bool = Field(False, description="是否有背景图")
    has_thumbnail: bool = Field(False, description="是否有缩略图")

    is_deleted: bool = Field(False, description="软删除标记")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    created_at: datetime = Field(None, description="创建时间")
    updated_at: datetime = Field(None, description="更新时间")


class MovieRead(MovieInDB):
    """读取电影响应模型"""

    pass


class MovieReadWithFlags(MovieRead):
    is_favoriter: Optional[bool] = Field(None, description="当前用户是否收藏了该影片")
    is_watchLater: Optional[bool] = Field(None, description="当前用户是否加入了稍后观看")


class MoviePageResult(BaseModel):
    """电影分页结果模型"""

    items: List[MovieRead | MovieInDB] = Field(default_factory=list, description="电影列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

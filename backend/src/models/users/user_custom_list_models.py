from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class CustomListType(str, Enum):
    """自定义片单类型"""

    FAVORITE = "favorite"  # 用户最爱
    WATCHLIST = "watchlist"  # 用户观看列表
    CUSTOMLIST = "customlist"  # 用户自定义片单


class CustomListBase(BaseModel):
    name: str = Field(..., description="片单名称")
    type: CustomListType = Field(..., description="片单类型")
    description: Optional[str] = Field("", description="片单描述")
    movies: List[str] = Field(default_factory=list, description="电影ID列表")
    is_public: bool = Field(False, description="是否公开")


class CustomListCreate(CustomListBase):
    user_id: str = Field(..., description="所属用户ID")


class CustomListUpdate(BaseModel):
    name: Optional[str] = Field(None, description="片单名称")
    description: Optional[str] = Field(None, description="片单描述")
    movies: Optional[List[str]] = Field(None, description="电影ID列表")


class CustomListInDB(CustomListBase):
    id: str = Field(..., description="片单唯一ID")
    user_id: str = Field(..., description="所属用户ID")
    movies: List[str] = Field(default_factory=list, description="电影ID列表")

    is_deleted: bool = Field(False, description="软删除标记")
    deleted_at: Optional[datetime] = Field(None, description="删除时间")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class CustomListRead(CustomListInDB):
    pass


class CustomListPageResult(BaseModel):
    items: List[CustomListRead | CustomListInDB] = Field(default_factory=list, description="片单列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

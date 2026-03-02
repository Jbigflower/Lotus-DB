"""
用户基础信息模型
包含高频收藏/片单内嵌，支持用户设置和权限管理
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, EmailStr
from enum import Enum
from .user_asset_models import UserAssetType


class UserRole(str, Enum):
    """用户角色枚举"""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class UserSettings(BaseModel):
    """用户设置子模型"""

    theme: str = Field("light", description="主题设置")
    language: str = Field("en-US", description="语言设置")
    auto_play: bool = Field(True, description="自动播放")
    subtitle_enabled: bool = Field(True, description="默认启用字幕")
    quality_preference: str = Field("auto", description="画质偏好")


class UserBase(BaseModel):
    """用户的通用字段（跨 DB/Read 层复用）"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    role: UserRole = UserRole.USER
    permissions: List[str] = Field(
        default_factory=list, description="额外权限"
    )  # TODO 后期构筑
    is_active: bool = Field(True, description="是否激活")
    is_verified: bool = Field(True, description="是否验证邮箱")  # TODO 后期构筑
    settings: UserSettings = Field(default_factory=UserSettings, description="用户设置")


class UserCreate(UserBase):
    """入库创建模型（仓储层验证使用）"""

    hashed_password: str = Field(..., description="加密密码")


class UserUpdate(BaseModel):
    """更新用户请求模型（部分字段可选）"""

    # 单独实现特殊函数进行修改
    # username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
    # email: Optional[EmailStr] = Field(None, description="邮箱")
    # role: Optional[UserRole] = Field(None, description="用户角色")
    # is_active: Optional[bool] = Field(None, description="是否激活")
    # is_verified: Optional[bool] = Field(None, description="是否验证邮箱")
    settings: Optional[UserSettings] = Field(None, description="用户设置")


class UserInDB(UserBase):
    """数据库中的用户模型"""

    id: str = Field(..., description="用户ID")
    hashed_password: str = Field(..., description="加密密码")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
    # is_deleted: bool = Field(False, description="软删除标记")
    # deleted_at: Optional[datetime] = Field(None, description="删除时间")
    created_at: datetime = Field(None, description="创建时间")
    updated_at: datetime = Field(None, description="更新时间")


class UserRead(UserInDB):
    """读取用户响应模型"""

    hashed_password: Optional[str] = Field(None, description="加密密码", exclude=True)


class UserPageResult(BaseModel):
    """用户分页结果模型"""

    items: List[UserRead | UserInDB] = Field(default_factory=list, description="用户列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

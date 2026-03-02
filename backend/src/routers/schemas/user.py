from typing import List, Optional, Union
from pydantic import BaseModel, Field, EmailStr
from src.models import UserCreate, UserUpdate, UserRead, UserPageResult, UserRole


class UserCreateRequestSchema(UserCreate):
    """创建用户请求模型"""

    password: str = Field(..., min_length=8, description="明文密码")
    hashed_password: Optional[str] = Field(
        None, description="加密密码，系统自动生成", exclude=True
    )


class UserUpdateRequestSchema(UserUpdate):
    """更新用户请求模型"""

    pass  # 所有字段从 UserUpdate 继承


class UserReadResponseSchema(UserRead):
    """读取用户响应模型"""

    pass  # 所有字段从 UserRead 继承，Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return UserRead


class UserPageResultResponseSchema(UserPageResult):
    """用户分页结果响应模型"""

    pass


class StatusPatchResponseSchema(BaseModel):
    """状态更新响应模型"""

    status: str = Field(..., description="操作状态")
    user: UserRead = Field(..., description="用户信息")


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6, description="新密码（明文）")


class UserPasswordChange(BaseModel):
    old_password: str = Field(..., min_length=6, description="旧密码（明文）")
    new_password: str = Field(..., min_length=6, description="新密码（明文）")


class UserIdentityUpdate(BaseModel):
    username: Optional[str] = Field(
        None, min_length=2, max_length=50, description="新用户名"
    )
    email: Optional[EmailStr] = Field(None, description="新邮箱")


# 新增：角色权限更新请求模型
class UserRolePermissionsUpdateRequestSchema(BaseModel):
    role: UserRole = Field(..., description="用户角色")
    permissions: Optional[List[str]] = Field(None, description="权限列表")

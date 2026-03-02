# 顶部：统一引入 Request、router_handler、路由级日志
from fastapi import APIRouter
from fastapi import Depends, HTTPException, status, Query, Path, Body, Request
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from src.core.dependencies import get_current_user
from src.services import UserService
from src.models import UserCreate, UserUpdate, UserRead, UserPageResult, UserRole
from src.routers.schemas.user import (
    UserPasswordReset,
    UserPasswordChange,
    UserIdentityUpdate,
    UserCreateRequestSchema,
    UserUpdateRequestSchema,
    UserReadResponseSchema,
    UserPageResultResponseSchema,
    UserRolePermissionsUpdateRequestSchema,
)
from src.core.handler import router_handler
from config.logging import get_router_logger
from fastapi import UploadFile, File

router = APIRouter(prefix="/api/v1/users", tags=["Users"])
service = UserService()
logger = get_router_logger("users")


@router.get("/ping")
@router_handler(action="ping")
async def ping(request: Request):
    return {"status": "ok", "router": "Users"}


@router.get("/", response_model=UserPageResultResponseSchema)
@router_handler(action="list_users")
async def list_users(
    request: Request,
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页大小"),
    query: Optional[str] = Query(None, description="用户名/邮箱模糊搜索"),
    role: Optional[UserRole] = Query(None, description="角色过滤"),
    is_active: Optional[bool] = Query(None, description="激活状态过滤"),
    is_verified: Optional[bool] = Query(None, description="邮箱验证状态过滤"),
):
    result = await service.list_users(
        current_user=current_user,
        page=page,
        size=size,
        query=query,
        role=role,
        is_active=is_active,
        is_verified=is_verified,
    )
    return result

@router.get("/mapping", response_model=Dict[str, str])
@router_handler(action="get_user_id_mapping")
async def get_user_mapping(
    request: Request,
    ids: str = Query(..., description="用户ID列表，用逗号分隔"),
    current_user=Depends(get_current_user),
):
    user_ids = ids.split(",")
    users = await service.get_user_mappings(user_ids, current_user)
    return users


@router.get("/{user_id}", response_model=UserReadResponseSchema)
@router_handler(action="get_user_detail")
async def get_user_detail(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    current_user=Depends(get_current_user),
):
    user = await service.get_user_detail(user_id, current_user)
    return user

# Create
@router.post("/", response_model=UserReadResponseSchema)
@router_handler(action="create_user")
async def create_user(
    request: Request,
    data: UserCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    # 路由层转换为 Model 层 payload + 上下文
    doc = data.model_dump()
    plain = doc.pop("password", None)
    payload = {
        "username": doc.get("username"),
        "email": doc.get("email"),
        "role": doc.get("role", UserRole.USER),
        "permissions": doc.get("permissions", []),
        "is_active": doc.get("is_active", True),
        "is_verified": doc.get("is_verified", True),
        "settings": doc.get("settings"),
    }
    context = {
        "plain_password": plain,
        "actor_id": str(getattr(current_user, "id", "")),
        "is_admin": getattr(current_user, "role", None) == UserRole.ADMIN,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent"),
    }
    user = await service.create_user(payload, context, current_user)
    return user

# Update（按规范进行编排）
@router.patch("/{user_id}", response_model=UserReadResponseSchema)
@router_handler(action="update_user")
async def update_user(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    data: UserUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    patch = data.model_dump(exclude_none=True)
    updated = await service.update_user_safety(user_id, patch, current_user)
    return updated

@router.patch("/{user_id}/activate", response_model=UserReadResponseSchema)
@router_handler(action="activate_user")
async def activate_user(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    is_active: bool = Body(..., description="是否激活"),
    current_user=Depends(get_current_user),
):
    updated = await service.set_user_active_status(user_id, is_active, current_user)
    return updated

@router.patch("/{user_id}/role", response_model=UserReadResponseSchema)
@router_handler(action="set_role_permissions")
async def set_role_permissions(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    data: UserRolePermissionsUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    updated = await service.set_role_permissions(
        user_id, data.role, data.permissions, current_user
    )
    return updated

@router.patch("/{user_id}/password/reset", response_model=UserReadResponseSchema)
@router_handler(action="reset_password")
async def reset_password(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    data: UserPasswordReset = Body(...),
    current_user=Depends(get_current_user),
):
    payload = data.model_dump()
    updated = await service.reset_password(user_id, payload, current_user)
    return updated

@router.patch("/{user_id}/password/change", response_model=UserReadResponseSchema)
@router_handler(action="change_password")
async def change_password(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    data: UserPasswordChange = Body(...),
    current_user=Depends(get_current_user),
):
    payload = data.model_dump()
    updated = await service.change_password(user_id, payload, current_user)
    return updated

@router.patch("/{user_id}/identity", response_model=UserReadResponseSchema)
@router_handler(action="update_identity")
async def update_identity(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    data: UserIdentityUpdate = Body(...),
    current_user=Depends(get_current_user),
):
    payload = data.model_dump(exclude_none=True)
    updated = await service.update_identity(user_id, payload, current_user)
    return updated

# Delete（固定返回字典）
@router.delete("/{user_id}", response_model=dict)
@router_handler(action="delete_user")
async def delete_user(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    current_user=Depends(get_current_user),
):
    user_model, meta = await service.delete_user(user_id, current_user)
    # 统一删除返回格式；如有任务信息，可在此统一附加
    return {
        "message": meta.get("message", ""),
        "success": meta.get("success", 0),
    }

# ---- 获取用户头像签名（批量） ---- #
@router.post("/profiles/sign", response_model=List[str])
@router_handler(action="get_user_profiles_signed")
async def get_user_profiles_signed(
    request: Request,
    ids: List[str] = Body(..., description="用户ID列表"),
    current_user=Depends(get_current_user),
):
    """
    批量返回用户头像（profile.jpg）的 Nginx 签名 URL 列表。
    - 鉴权在服务层进行（管理员或已登录用户）
    - 资产路径通过 UserAssetFileOps.get_user_profile_path 获取
    - 使用 Nginx 分发具体文件（secure_link）
    """
    return await service.list_user_profiles_signed(ids, current_user=current_user)

# ---- 上传用户头像（Upload） ---- #
@router.post("/{user_id}/profile", response_model=Dict[str, Any])
@router_handler(action="upload_user_profile")
async def upload_user_profile(
    request: Request,
    user_id: str = Path(..., description="用户ID"),
    file: UploadFile = File(..., description="头像文件（multipart/form-data: file）"),
    current_user=Depends(get_current_user),
):
    ok = await service.upload_user_profile(user_id, file, current_user=current_user)
    return {"message": "上传头像成功", "ok": ok}

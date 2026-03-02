# 顶层模块 import（移除未使用的 Security、oauth2_scheme）
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from src.services import AuthService
from src.core.dependencies import get_current_user

from src.routers.schemas.auth import TokenResponse, AvailabilityResponse, EmailVerifySendRequest, EmailVerifyConfirmRequest
from src.routers.schemas.user import UserCreateRequestSchema

from src.core.handler import router_handler
from config.logging import get_router_logger

router = APIRouter(prefix="/auth", tags=["Auth"])
service = AuthService()
logger = get_router_logger("auth")


@router.post("/register", response_model=TokenResponse)
@router_handler(action="register")
async def register(request: Request, data: UserCreateRequestSchema = Body(...)):
    """
    用户注册：
    - 提交用户名、邮箱、密码
    - 创建用户后自动登录，返回 JWT + 用户信息
    """
    _ = await service.register(data)
    # 注册成功后自动登录，复用现有 AuthService 的登录逻辑（含会话缓存）
    result = await service.login(username=data.username, password=data.password)
    return TokenResponse(**result)


# function: router endpoints (login/logout and new devices routes)
from typing import List
from src.core.dependencies import get_current_session
from src.routers.schemas.auth import TokenResponse, DeviceSessionRead
from fastapi import Query
from pydantic import EmailStr

@router.post("/login", response_model=TokenResponse)
@router_handler(action="login")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    device_info = {
        "user_agent": request.headers.get("user-agent"),
        "ip": request.headers.get("x-forwarded-for") or (request.client.host if request.client else None),
        "platform": request.headers.get("x-platform"),
    }
    result = await service.login(
        username=form_data.username, password=form_data.password, device_info=device_info
    )
    return TokenResponse(**result)


@router.post("/logout", response_model=dict)
@router_handler(action="logout")
async def logout(request: Request, current_user=Depends(get_current_user), current_session=Depends(get_current_session)):
    await service.logout(user_id=current_user.id, session_id=current_session.session_id)
    return {"status": "success"}


@router.get("/devices", response_model=List[DeviceSessionRead])
@router_handler(action="list_devices")
async def list_devices(request: Request, current_user=Depends(get_current_user), current_session=Depends(get_current_session)):
    sessions = await service.list_devices(user_id=current_user.id)
    current_sid = current_session.session_id
    items = []
    for s in sessions:
        s["is_current"] = (s.get("session_id") == current_sid)
        items.append(s)
    return items

@router.post("/devices/revoke/{session_id}", response_model=dict)
@router_handler(action="revoke_device")
async def revoke_device(request: Request, session_id: str, current_user=Depends(get_current_user)):
    await service.revoke_device(user_id=current_user.id, session_id=session_id)
    return {"status": "success"}

@router.post("/devices/revoke_all", response_model=dict)
@router_handler(action="revoke_all_devices")
async def revoke_all_devices(request: Request, current_user=Depends(get_current_user), current_session=Depends(get_current_session)):
    await service.revoke_all_devices(user_id=current_user.id, except_session_id=current_session.session_id)
    return {"status": "success"}

@router.patch("/devices/{session_id}", response_model=dict)
@router_handler(action="rename_device")
async def rename_device(request: Request, session_id: str, alias: str = Body(..., embed=True), current_user=Depends(get_current_user)):
    await service.rename_device(user_id=current_user.id, session_id=session_id, alias=alias)
    return {"status": "success"}

@router.get("/availability/username", response_model=dict)
@router_handler(action="check_username_availability")
async def check_username_availability(request: Request, username: str = Query(..., min_length=2, max_length=50)):
    available = await service.check_username_availability(username)
    return {"available": available}

@router.get("/availability/email", response_model=dict)
@router_handler(action="check_email_availability")
async def check_email_availability(request: Request, email: EmailStr = Query(...)):
    available = await service.check_email_availability(str(email))
    return {"available": available}

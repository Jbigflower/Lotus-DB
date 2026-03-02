from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from src.models import UserRead


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    session_id: Optional[str] = None

class AvailabilityResponse(BaseModel):
    available: bool

class DeviceSessionRead(BaseModel):
    session_id: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    platform: Optional[str] = None
    alias: Optional[str] = None
    created_at: datetime
    last_active_at: Optional[datetime] = None
    is_current: bool = False

class EmailVerifySendRequest(BaseModel):
    email: EmailStr = Field(..., description="邮箱")

class EmailVerifyConfirmRequest(BaseModel):
    email: EmailStr = Field(..., description="邮箱")
    code: str = Field(..., min_length=4, max_length=10, description="验证码")

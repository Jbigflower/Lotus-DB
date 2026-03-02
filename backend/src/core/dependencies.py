# module-level definitions
from typing import Optional
from fastapi import HTTPException, status, Security, Depends, Query
from fastapi.security import OAuth2PasswordBearer
from src.models import UserRead, LibraryRead
from src.services import AuthService
from src.logic import LibraryLogic

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)  # 登录接口返回 token
auth_service = AuthService()
library_logic = LibraryLogic()


async def get_current_user(
    token: Optional[str] = Security(oauth2_scheme),
    query_token: Optional[str] = Query(None, alias="token"),
) -> UserRead:
    # 优先使用 Header 中的 Bearer Token，若无则尝试 Query Param
    final_token = token or query_token
    
    if not final_token:
         raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 使用服务层校验 token 和 Redis 会话一致性，而非直接通过 Repo
    try:
        current = await auth_service.verify_token(final_token)
        return current
    except HTTPException:
        # 维持原有异常语义与 header
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_library(
    current_user: UserRead = Depends(get_current_user),
) -> Optional[LibraryRead]:
    """
    依赖注入：获取当前库信息
    从Redis缓存中读取用户当前库信息
    """
    try:
        library = await library_logic.get_current_library(current_user.id)
        return library
    except Exception as e:
        # 如果获取当前库失败，返回None而不是抛出异常
        # 这样可以让路由处理器决定如何处理没有当前库的情况
        return None


# function: get_current_session()
from fastapi import Security, HTTPException, status
from pydantic import BaseModel
from jose import JWTError, jwt
from config.setting import settings

class CurrentSession(BaseModel):
    session_id: str
    user_id: str
    token: str

async def get_current_session(token: str = Security(oauth2_scheme)) -> CurrentSession:
    try:
        payload = jwt.decode(token, settings.app.secret_key, algorithms=[settings.app.algorithm])
        sid = payload.get("sid")
        sub = payload.get("sub")
        if not sid or not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的会话令牌")
        return CurrentSession(session_id=sid, user_id=sub, token=token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌已过期或无效")

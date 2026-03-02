# 模块：AuthLogic 及模块级 JWT 帮助方法

from typing import Optional
from hashlib import sha256
import secrets
import string
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from pydantic import BaseModel

from src.repos import UserRepo, UserRedisRepo
from src.models import UserRead, UserCreate, UserRole
from config.setting import settings
from src.core.exceptions import (
    UnauthorizedError,
    ConflictError,
    ValidationError,
)
from src.core.handler import logic_handler
from config.logging import get_logic_logger

# 注入 JWT 配置到本模块
SECRET_KEY = settings.app.secret_key
ALGORITHM = settings.app.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.app.access_token_expire_minutes

from uuid import uuid4

class TokenData(BaseModel):
    user_id: str
    session_id: Optional[str] = None

def create_access_token(user_id: str, session_id: Optional[str] = None, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = {"sub": user_id}
    if session_id:
        to_encode["sid"] = session_id
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        session_id: Optional[str] = payload.get("sid")
        if user_id is None:
            raise ValueError("Token 无效")
        return TokenData(user_id=user_id, session_id=session_id)
    except JWTError:
        raise ValueError("Token 无效或已过期")


class AuthLogic:
    """
    鉴权逻辑层：
    - 登录：用户查找、密码校验、创建 JWT、缓存会话、更新最后登录
    - 注销：撤销 Redis 中的会话
    - 验证：校验 token、用户状态与 Redis 会话一致性
    """

    def __init__(self) -> None:
        self.user_repo = UserRepo()
        self.user_cache = UserRedisRepo()
        self.logger = get_logic_logger("auth_logic")

    def _hash_password(self, password: str) -> str:
        salt = settings.app.secret_key or ""
        return sha256((salt + password).encode("utf-8")).hexdigest()

    @logic_handler("检查用户名可用性")
    async def is_username_available(self, username: str, session=None) -> bool:
        existed = await self.user_repo.exists({"username": username}, session=session)
        return not existed

    @logic_handler("检查邮箱可用性")
    async def is_email_available(self, email: str, session=None) -> bool:
        existed = await self.user_repo.exists({"email": email}, session=session)
        return not existed

    @logic_handler("发送邮箱验证码")
    async def send_email_verification(self, email: str) -> bool:
        available = await self.is_email_available(email)
        if not available:
            raise ConflictError("邮箱已存在")
        code = "".join(secrets.choice(string.digits) for _ in range(6))
        ok = await self.user_cache.set_email_verify_code(email, code, expire=300)
        if not ok:
            raise ValidationError("验证码生成失败")
        # 暂无邮件发送通道，记录日志用于开发调试
        self.logger.info(f"邮箱验证码已生成 email={email} code={code}")
        return True

    @logic_handler("验证邮箱验证码")
    async def verify_email_code(self, email: str, code: str) -> bool:
        cached = await self.user_cache.get_email_verify_code(email)
        if not cached:
            raise ValidationError("验证码不存在或已过期")
        if str(cached) != str(code):
            raise ValidationError("验证码不正确")
        await self.user_cache.delete_email_verify_code(email)
        return True

    @logic_handler("注册用户")
    async def register(self, payload: UserCreate, session=None) -> UserRead:
        existed_by_name = await self.user_repo.exists(
            {"username": payload.username}, session=session
        )
        if existed_by_name:
            raise ConflictError("用户名已存在")
        existed_by_email = await self.user_repo.exists(
            {"email": payload.email}, session=session
        )
        if existed_by_email:
            raise ConflictError("邮箱已存在")

        created = await self.user_repo.insert_one(payload, session=session)
        return UserRead.model_validate(created.model_dump(exclude={"hashed_password"}))

    @logic_handler("检查用户名可用性")
    async def is_username_available(self, username: str, session=None) -> bool:
        return not await self.user_repo.exists({"username": username}, session=session)

    @logic_handler("检查邮箱可用性")
    async def is_email_available(self, email: str, session=None) -> bool:
        return not await self.user_repo.exists({"email": email}, session=session)

    @logic_handler("登录用户")
    async def login(
        self, username: str, password: str, session=None, device_info: Optional[dict] = None
    ) -> tuple[str, UserRead, str]:
        # 适配仓储简化：使用通用 find 进行用户名/邮箱查询
        found = await self.user_repo.find(
            filter_query={"username": username},
            limit=1,
            session=session,
        )
        user = found[0] if found else None
        if not user:
            found = await self.user_repo.find(
                filter_query={"email": username},
                limit=1,
                session=session,
            )
            user = found[0] if found else None

        if not user:
            raise UnauthorizedError("认证失败")
        if not user.is_active:
            raise UnauthorizedError("用户未激活或已停用")

        hashed = self._hash_password(password)
        if hashed != user.hashed_password:
            raise UnauthorizedError("认证失败")

        # 适配仓储简化：使用通用 update_by_id 更新最后登录时间
        user = await self.user_repo.update_by_id(
            user.id, {"last_login_at": datetime.now(timezone.utc)}, session=session
        )

        token_session_id = uuid4().hex
        token = create_access_token(user.id, session_id=token_session_id)
        expire_seconds = int(ACCESS_TOKEN_EXPIRE_MINUTES) * 60
    
        # 保持用户信息缓存
        await self.user_cache.cache_user_info(
            user.id, user.model_dump(exclude={"hashed_password"}), expire=expire_seconds
        )
    
        # 新增设备会话缓存
        await self.user_cache.add_device_session(
            user.id,
            token_session_id,
            token,
            {
                "user_agent": (device_info or {}).get("user_agent"),
                "ip": (device_info or {}).get("ip"),
                "platform": (device_info or {}).get("platform"),
            },
            expire=expire_seconds,
        )
        user_read = UserRead.model_validate(user.model_dump(exclude={"hashed_password"}))
        return (token, user_read, token_session_id)

    async def logout(self, user_id: str, session_id: Optional[str] = None, session=None) -> None:
        if session_id:
            await self.user_cache.revoke_device_session(user_id, session_id)
        else:
            await self.user_cache.clear_user_cache(user_id)

    async def verify_token(self, token: str, session=None) -> UserRead:
        token_data = verify_access_token(token)
        if token_data.session_id:
            session_rec = await self.user_cache.get_device_session(token_data.user_id, token_data.session_id)
            if not session_rec:
                raise UnauthorizedError("会话已失效")
            if session_rec.get("token") != token:
                raise UnauthorizedError("会话令牌不匹配")
            user_info = await self.user_cache.get_user_info(token_data.user_id)
        else:
            cached = await self.user_cache.get_user_session(token_data.user_id)
            if not cached or cached["jwt"] != token:
                raise UnauthorizedError("会话已失效或令牌不匹配")
            user_info = cached["user"]
    
        if not user_info.get("is_active", True):
            raise UnauthorizedError("用户未激活或已停用")
        return UserRead.model_validate(user_info)

    @logic_handler("列出设备会话")
    async def list_devices(self, user_id: str, session=None) -> list[dict]:
        return await self.user_cache.list_device_sessions(user_id)

    @logic_handler("撤销设备会话")
    async def revoke_device(self, user_id: str, session_id: str, session=None) -> None:
        await self.user_cache.revoke_device_session(user_id, session_id)

    @logic_handler("撤销所有设备会话")
    async def revoke_all_devices(self, user_id: str, except_session_id: Optional[str] = None, session=None) -> None:
        await self.user_cache.revoke_all_sessions(user_id, except_session_id=except_session_id)

    @logic_handler("重命名设备会话")
    async def rename_device(self, user_id: str, session_id: str, alias: str, session=None) -> None:
        await self.user_cache.update_device_alias(user_id, session_id, alias)

    @logic_handler("初始化管理员账号")
    async def init_admin_account(self, session=None) -> None:
        """应用启动时检查并创建默认管理员"""
        # 1. 检查是否存在管理员
        admins = await self.user_repo.find(
            filter_query={"role": UserRole.ADMIN.value},
            limit=1,
            session=session
        )
        if admins:
            self.logger.info("管理员账号已存在，跳过初始化")
            return

        # 2. 读取配置
        admin_user = settings.app.admin_username
        admin_pass = settings.app.admin_password
        
        # 3. 检查默认用户名是否已被占用
        if not await self.is_username_available(admin_user, session=session):
             self.logger.warning(f"默认管理员用户名 {admin_user} 已被占用，跳过创建")
             return

        # 4. 创建管理员
        hashed = self._hash_password(admin_pass)
        new_admin = UserCreate(
            username=admin_user,
            email="admin@lotus.db", # 默认邮箱
            hashed_password=hashed,
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True
        )
        
        # 使用 insert_many 因为 BaseRepo 可能只提供了 insert_many，或者 insert_one 是便捷封装
        # 根据 register 方法，insert_one 是存在的。
        await self.user_repo.insert_one(new_admin, session=session)
        self.logger.info(f"默认管理员账号已创建: {admin_user}")

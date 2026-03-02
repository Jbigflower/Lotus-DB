from src.logic import AuthLogic, CollectionLogic
from src.models import UserRead, UserCreate
from src.routers.schemas.user import UserCreateRequestSchema
from src.core.handler import service_handler
from config.logging import get_service_logger

class AuthService:
    """
    鉴权服务层：
    - 异常转换为统一业务异常（由 handler 层映射为 HTTP 异常）
    - 负责权限判定（如用户状态）
    - 委托逻辑层执行核心业务
    """

    def __init__(self) -> None:
        self.logic = AuthLogic()
        self.logger = get_service_logger("auth_service")
        self.collection_logic = CollectionLogic()

    @service_handler(action="register")
    async def register(self, payload: UserCreateRequestSchema) -> UserRead:
        hashed_password = self.logic._hash_password(payload.password)
        data = payload.model_dump(exclude={"password"}) | {
            "hashed_password": hashed_password
        }
        user_read = await self.logic.register(UserCreate(**data))
        try:
            await self.collection_logic.init_default(user_read.id)
        except Exception as e:
            self.logger.warning(f"初始化默认片单失败: {e}")
        return user_read

    @service_handler(action="login")
    async def login(self, username: str, password: str, device_info: dict | None = None) -> dict:
        token, user_read, session_id = await self.logic.login(username, password, device_info=device_info)
        return {"access_token": token, "token_type": "bearer", "user": user_read, "session_id": session_id}

    @service_handler(action="check_username")
    async def check_username(self, username: str) -> dict:
        available = await self.logic.is_username_available(username)
        return {"available": available}

    @service_handler(action="check_email")
    async def check_email(self, email: str) -> dict:
        available = await self.logic.is_email_available(email)
        return {"available": available}

    @service_handler(action="send_email_code")
    async def send_email_code(self, email: str) -> dict:
        await self.logic.send_email_verification(email)
        return {"status": "sent"}

    @service_handler(action="confirm_email_code")
    async def confirm_email_code(self, email: str, code: str) -> dict:
        await self.logic.verify_email_code(email, code)
        return {"status": "verified"}

    @service_handler(action="logout")
    async def logout(self, user_id: str, session_id: str | None = None) -> dict:
        await self.logic.logout(user_id, session_id=session_id)
        return {"status": "success"}

    @service_handler(action="list_devices")
    async def list_devices(self, user_id: str) -> list[dict]:
        return await self.logic.list_devices(user_id)

    @service_handler(action="revoke_device")
    async def revoke_device(self, user_id: str, session_id: str) -> dict:
        await self.logic.revoke_device(user_id, session_id)
        return {"status": "success"}

    @service_handler(action="revoke_all_devices")
    async def revoke_all_devices(self, user_id: str, except_session_id: str | None = None) -> dict:
        await self.logic.revoke_all_devices(user_id, except_session_id=except_session_id)
        return {"status": "success"}

    @service_handler(action="rename_device")
    async def rename_device(self, user_id: str, session_id: str, alias: str) -> dict:
        await self.logic.rename_device(user_id, session_id, alias)
        return {"status": "success"}

    @service_handler(action="check_username_availability")
    async def check_username_availability(self, username: str) -> bool:
        return await self.logic.is_username_available(username)

    @service_handler(action="check_email_availability")
    async def check_email_availability(self, email: str) -> bool:
        return await self.logic.is_email_available(email)

    @service_handler(action="verify_token")
    async def verify_token(self, token: str) -> UserRead:
        """
        供依赖层调用：
        - 校验 JWT 有效性
        - 校验用户存在、活跃状态
        - 校验 Redis 中的会话与传入 token 一致（未撤销）
        返回简化的 current_user 对象（id/username/is_admin/role）
        """
        current_user = await self.logic.verify_token(token)
        return current_user

# 顶部 imports 调整：移除所有 schemas 相关导入
from typing import Optional, List, Dict, Any
from src.logic import UserLogic, CollectionLogic
from src.models import UserCreate, UserUpdate, UserRead, UserPageResult, UserRole
from src.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from src.core.handler import service_handler
from config.logging import get_service_logger
from fastapi import UploadFile
from src.logic.file.user_asset_file_ops import UserAssetFileOps

class UserService:
    """
    用户服务层
    - 权限校验、异常转换（业务异常）
    - 委托逻辑层执行核心业务
    """

    def __init__(self) -> None:
        self.logic = UserLogic()
        self.logger = get_service_logger("user_service")
        self.file_logic = UserAssetFileOps()
        self.collection_logic = CollectionLogic()

    def _ensure_admin(self, current_user) -> None:
        if getattr(current_user, "role", None) != UserRole.ADMIN:
            raise ForbiddenError("无权限")

    @service_handler(action="list_users")
    async def list_users(
        self,
        current_user,
        page: int = 1,
        size: int = 20,
        query: Optional[str] = None,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None,
    ) -> UserPageResult:
        self._ensure_admin(current_user)
        return await self.logic.search_users(
            query, role, is_active, is_verified, page, size
        )

    @service_handler(action="get_user_detail")
    async def get_user_detail(self, user_id: str, current_user) -> UserRead:
        user = await self.logic.get_user(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        if getattr(current_user, "role", None) != UserRole.ADMIN and str(
            current_user.id
        ) != str(user_id):
            raise ForbiddenError("无权限")
        return user

    @service_handler(action="get_user_mappings")
    async def get_user_mappings(self, user_ids: List[str], current_user) -> UserRead:
        users = await self.logic.get_users(user_ids)
        return {u.id: u.username for u in users}

    @service_handler(action="create_user")
    async def create_user(
        self,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        current_user,
    ) -> UserRead:
        self._ensure_admin(current_user)
        doc = dict(payload or {})
        plain = context.get("plain_password") or doc.pop("password", None)
        if not plain:
            raise ValidationError("缺少密码")
        doc["hashed_password"] = self.logic._hash_password(plain)
        created = await self.logic.create_user(UserCreate(**doc))
        try:
            await self.collection_logic.init_default(created.id)
        except Exception as e:
            self.logger.warning(f"初始化默认片单失败: {e}")
        return created

    @service_handler(action="update_user")
    async def update_user_safety(
        self, user_id: str, patch: Dict[str, Any], current_user
    ) -> UserRead:
        is_admin = getattr(current_user, "role", None) == UserRole.ADMIN
        is_self = str(current_user.id) == str(user_id)
        if not is_admin and (not is_self):
            raise ForbiddenError("无权限")
        updated = await self.logic.update_user_safety(user_id, patch)
        return updated

    @service_handler(action="set_role_permissions")
    async def set_role_permissions(
        self,
        user_id: str,
        role: Optional[UserRole],
        permissions: Optional[List[str]],
        current_user,
    ) -> UserRead:
        self._ensure_admin(current_user)
        updated = await self.logic.set_user_role_permissions(user_id, role, permissions)
        return updated

    @service_handler(action="reset_password")
    async def reset_password(
        self, user_id: str, payload: Dict[str, Any], current_user
    ) -> UserRead:
        self._ensure_admin(current_user)
        new_plain = payload.get("new_password")
        if not new_plain:
            raise ValidationError("缺少新密码")
        new_hashed = self.logic._hash_password(new_plain)
        updated = await self.logic.update_user_safety(
            user_id, {"hashed_password": new_hashed}
        )
        return updated

    @service_handler(action="change_password")
    async def change_password(
        self, user_id: str, payload: Dict[str, Any], current_user
    ) -> UserRead:
        is_admin = getattr(current_user, "role", None) == UserRole.ADMIN
        is_self = str(current_user.id) == str(user_id)
        if not is_admin and (not is_self):
            raise ForbiddenError("无权限")
        old_plain = payload.get("old_password")
        new_plain = payload.get("new_password")
        if not old_plain or not new_plain:
            raise ValidationError("缺少密码参数")

        # 校验原密码（UserRead 不包含 hashed，额外查询 InDB）
        full = await self.logic.repo.find_by_id(user_id)
        if not full:
            raise NotFoundError("用户不存在")
        old_hashed = self.logic._hash_password(old_plain)
        if old_hashed != full.hashed_password:
            raise ValidationError("原密码不正确")

        new_hashed = self.logic._hash_password(new_plain)
        updated = await self.logic.update_user_safety(
            user_id, {"hashed_password": new_hashed}
        )
        return updated

    @service_handler(action="update_identity")
    async def update_identity(
        self, user_id: str, payload: Dict[str, Any], current_user
    ) -> UserRead:
        is_admin = getattr(current_user, "role", None) == UserRole.ADMIN
        is_self = str(current_user.id) == str(user_id)
        if not is_admin and (not is_self):
            raise ForbiddenError("无权限")

        username = payload.get("username")
        email = payload.get("email")
        if not username and not email:
            raise ValidationError("至少提供用户名或邮箱之一")

        patch: Dict[str, Any] = {}
        if username:
            patch["username"] = username
        if email:
            patch["email"] = email

        updated = await self.logic.update_username_or_email(user_id, patch)
        return updated

    @service_handler(action="delete_user")
    async def delete_user(
        self, user_id: str, current_user
    ) -> tuple[Optional[UserRead], Dict[str, Any]]:
        self._ensure_admin(current_user)

        # 删除前获取用户信息（用于返回 Model 层模型）
        try:
            user = await self.logic.get_user(user_id)
        except NotFoundError:
            return (None, {"message": "用户不存在或已删除", "success": 0, "failed": 1})

        ok = await self.logic.delete_user(user_id)

        meta = {
            "message": "用户删除成功" if ok else "用户不存在或已删除",
            "success": 1 if ok else 0,
            "failed": 0 if ok else 1,
        }
        return (user if ok else None, meta)

    @service_handler(action="set_user_active_status")
    async def set_user_active_status(
        self, user_id: str, is_active: bool, current_user
    ) -> UserRead:
        self._ensure_admin(current_user)
        updated = await self.logic.set_user_active_status(user_id, is_active)
        return updated

    # -------------------------- 用户头像签名（批量） -----------------------------
    @service_handler(action="list_user_profiles_signed")
    async def list_user_profiles_signed(self, ids: List[str], *, current_user) -> List[str]:
        # 任意已登录用户可获取头像签名；仅校验用户存在
        signed_url_list: List[str] = []
        for uid in ids:
            # 确认用户存在（便于返回 404）
            await self.logic.get_user(uid)
            url, _ = self.file_logic.get_user_profile_signed_url(uid)
            signed_url_list.append(url)
        return signed_url_list

    # ---- 上传用户头像（权限检查 + 文件保存） ---- #
    @service_handler(action="upload_user_profile")
    async def upload_user_profile(self, user_id: str, upload: UploadFile, *, current_user) -> bool:
        is_admin = getattr(current_user, "role", None) == UserRole.ADMIN
        is_self = str(current_user.id) == str(user_id)
        if not is_admin and (not is_self):
            raise ForbiddenError("无权限")
        # 确认用户存在（便于返回 404）
        await self.logic.get_user(user_id)
        self.file_logic.save_user_profile(upload, user_id)
        return True

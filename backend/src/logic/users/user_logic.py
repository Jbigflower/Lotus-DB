from typing import Optional, List, Dict, Any
from hashlib import sha256
from pydantic import ValidationError as PydanticValidationError
from src.repos import UserRepo, UserRedisRepo
from src.models import (
    UserCreate,
    UserUpdate,
    UserRead,
    UserPageResult,
    UserRole,
)
from config.setting import get_settings
from src.core.exceptions import NotFoundError, ConflictError, ValidationError
from src.core.handler import logic_handler
from config.logging import get_logic_logger
from src.routers.schemas.user import (
    UserPasswordReset,
    UserPasswordChange,
    UserIdentityUpdate,
)


class UserLogic:
    """
    用户逻辑层
    - 核心业务规则与数据一致性校验
    - 不做权限判定（交由 Service）
    """

    def __init__(self) -> None:
        self.repo = UserRepo()
        self.cache_repo = UserRedisRepo()
        self.logger = get_logic_logger("user_logic")

    def _hash_password(self, password: str) -> str:
        settings = get_settings()
        salt = settings.app.secret_key or ""
        algorithm = settings.app.algorithm or "sha256"
        if algorithm.lower() in ("sha256", "hs256"):
            return sha256((salt + password).encode("utf-8")).hexdigest()
        raise ValidationError(f"不支持的加密算法: {algorithm}")

    @logic_handler("获取用户详情")
    async def get_user(self, user_id: str, session=None) -> Optional[UserRead]:
        cached = await self.cache_repo.get_user_info(user_id)
        if cached:
            return UserRead.model_validate(cached)
        user = await self.repo.find_by_id(user_id, session=session)
        if user:
            await self.cache_repo.cache_user_info(
                user_id, user.model_dump(exclude={"hashed_password"})
            )
            return UserRead.model_validate(user.model_dump(exclude={"hashed_password"}))
        raise NotFoundError("用户不存在")

    @logic_handler("获取多个用户详情")
    async def get_users(self, user_ids: List[str], session=None) -> Optional[UserRead]:
        if not user_ids:
            return []

        # 1) 尝试读取缓存
        id_to_read: Dict[str, UserRead] = {}
        missing_ids: List[str] = []

        for oid in user_ids:
            cached = await self.cache_repo.get_user_info(oid)
            if cached:
                try:
                    id_to_read[oid] = UserRead.model_validate(cached)
                except PydanticValidationError:
                    missing_ids.append(oid)
            else:
                missing_ids.append(oid)

        # 2) 对缺失部分回源并批量回填
        if missing_ids:
            db_items = await self.repo.find_by_ids(missing_ids, session=session)
            if db_items:
                payloads = [m.model_dump() for m in db_items]
                for m in db_items:
                    await self.cache_repo.cache_user_info(
                        m.id, m.model_dump(exclude={"hashed_password"})
                    )
                    id_to_read[m.id] = UserRead.model_validate(
                        m.model_dump(exclude={"hashed_password"})
                    )
        # 3) 按输入顺序返回（默认保持原顺序）
        result: List[UserRead] = [id_to_read[oid] for oid in user_ids if oid in id_to_read]
        return result


    @logic_handler("创建用户")
    async def create_user(self, data: UserCreate, session=None) -> UserRead:
        existed_by_name = await self.repo.exists(
            {"username": data.username}, session=session
        )
        if existed_by_name:
            raise ConflictError("用户名已存在")
        existed_by_email = await self.repo.exists(
            {"email": data.email}, session=session
        )
        if existed_by_email:
            raise ConflictError("邮箱已存在")
        created = await self.repo.insert_one(data, session=session)
        await self.cache_repo.cache_user_info(
            created.id, created.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(created.model_dump(exclude={"hashed_password"}))

    @logic_handler("更新用户（安全字段）")
    async def update_user_safety(
        self, user_id: str, patch: Dict[str, Any], session=None
    ) -> UserRead:
        updated = await self.repo.update_by_id(user_id, patch, session=session)
        await self.cache_repo.cache_user_info(
            user_id, updated.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(updated.model_dump(exclude={"hashed_password"}))

    # 丰富：删除用户（软/硬删除）
    @logic_handler("删除用户")
    async def delete_user(
        self, user_id: str, session=None
    ) -> bool:
        user = await self.repo.find_by_id(user_id, session=session)
        if not user:
            raise NotFoundError("用户不存在")
        ok = await self.repo.delete_by_id(user_id, soft_delete=False, session=session)
        await self.cache_repo.clear_user_cache(user_id)
        return ok > 0

    # 新增：重置密码（管理员）
    @logic_handler("重置用户密码")
    async def reset_password(
        self, user_id: str, data: UserPasswordReset, session=None
    ) -> UserRead:
        new_hashed = self._hash_password(data.new_password)
        updated = await self.repo.update_by_id(user_id, {"hashed_password": new_hashed}, session=session)
        await self.cache_repo.cache_user_info(
            user_id, updated.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(updated.model_dump(exclude={"hashed_password"}))

    # 新增：修改密码（本人或管理员）
    @logic_handler("修改用户密码")
    async def change_password(
        self, user_id: str, data: UserPasswordChange, session=None
    ) -> UserRead:
        user = await self.repo.find_by_id(user_id, session=session)
        if not user:
            raise NotFoundError("用户不存在")
        old_hashed = self._hash_password(data.old_password)
        if old_hashed != user.hashed_password:
            raise ValidationError("原密码不正确")
        new_hashed = self._hash_password(data.new_password)
        updated = await self.repo.update_by_id(user_id, {"hashed_password": new_hashed}, session=session)
        await self.cache_repo.cache_user_info(
            user_id, updated.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(updated.model_dump(exclude={"hashed_password"}))

    # 新增：更改用户名或邮箱（本人或管理员）
    @logic_handler("更改用户名或邮箱")
    async def update_username_or_email(
        self, user_id: str, data: UserIdentityUpdate, session=None
    ) -> UserRead:
        if not data.username and not data.email:
            raise ValidationError("至少提供用户名或邮箱之一")
        if data.username:
            existed_by_name = await self.repo.exists({"username": data.username}, session=session)
            if existed_by_name:
                raise ConflictError("用户名已存在")
        if data.email:
            existed_by_email = await self.repo.exists({"email": data.email}, session=session)
            if existed_by_email:
                raise ConflictError("邮箱已存在")

        patch: Dict[str, Any] = {}
        if data.username:
            patch["username"] = data.username
        if data.email:
            patch["email"] = data.email

        updated = await self.repo.update_by_id(user_id, patch, session=session)
        await self.cache_repo.cache_user_info(
            user_id, updated.model_dump(exclude={"hashed_password"})
        )
        return UserRead(**updated.model_dump(exclude={"hashed_password"}))

    @logic_handler("设置用户激活状态")
    async def set_user_active_status(
        self, user_id: str, is_active: bool, session=None
    ) -> UserRead:
        user = await self.get_user(user_id, session=session)
        if user.is_active == is_active:
            return user
        user_info = await self.repo.update_by_id(user_id, {"is_active": is_active}, session=session)
        await self.cache_repo.cache_user_info(
            user_id, user_info.model_dump(exclude={"hashed_password"})
        )
        return UserRead(**user_info.model_dump(exclude={"hashed_password"}))

    @logic_handler("更改用户权限")
    async def set_user_role_permissions(
        self, user_id: str, role: UserRole, permissions: List[str], session=None
    ) -> UserRead:
        patch = {}
        if role:
            patch["role"] = role
        if permissions is not None:
            patch["permissions"] = permissions
        user_info = await self.repo.update_by_id(user_id, patch, session=session)
        await self.cache_repo.cache_user_info(
            user_id, user_info.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(user_info.model_dump(exclude={"hashed_password"}))

    @logic_handler("设置用户邮箱验证状态")
    async def set_user_verify_status(
        self, user_id: str, is_verified: bool, session=None
    ) -> UserRead:
        updated = await self.repo.update_by_id(user_id, {"is_verified": is_verified}, session=session)
        await self.cache_repo.cache_user_info(
            user_id, updated.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(updated.model_dump(exclude={"hashed_password"}))

    @logic_handler("更新最后登录时间")
    async def touch_last_login(self, user_id: str, session=None) -> UserRead:
        from datetime import datetime, timezone
        updated = await self.repo.update_by_id(
            user_id, {"last_login_at": datetime.now(timezone.utc)}, session=session
        )
        await self.cache_repo.cache_user_info(
            user_id, updated.model_dump(exclude={"hashed_password"})
        )
        return UserRead.model_validate(updated.model_dump(exclude={"hashed_password"}))

    @logic_handler("搜索用户")
    async def search_users(
        self,
        query: Optional[str] = None,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None,
        page: int = 1,
        size: int = 20,
        session=None,
    ) -> UserPageResult:
        filter_dict: Dict[str, Any] = {}
        if self.repo.soft_delete:
            filter_dict["is_deleted"] = False
        if query:
            filter_dict["$or"] = [
                {"username": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
            ]
        if role:
            filter_dict["role"] = role.value
        if is_active is not None:
            filter_dict["is_active"] = is_active
        if is_verified is not None:
            filter_dict["is_verified"] = is_verified

        skip = max(page - 1, 0) * size
        results = await self.repo.find(
            filter_query=filter_dict,
            skip=skip,
            limit=size,
            sort=None,
            projection=None,
            session=session,
        )
        total = await self.repo.count(filter_dict, session=session)
        pages = (total + size - 1) // size

        # 将 InDB 转换为 Read（排除 hashed_password）
        items = [
            UserRead.model_validate(r.model_dump(exclude={"hashed_password"}))
            for r in results
        ]
        return UserPageResult(items=items, total=total, page=page, size=size, pages=pages)
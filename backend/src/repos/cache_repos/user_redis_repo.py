"""
用户缓存仓储层
存储会话(JWT)、偏好设置(UserSettings)与权限信息(UserRole/permissions)，严格继承 BaseRedisRepo。
"""

from typing import List, Optional, Dict, Any

from src.repos.cache_repos.base_redis_repo import BaseRedisRepo
from datetime import datetime, timezone


class UserRedisRepo(BaseRedisRepo):
    """用户 Redis 缓存仓储类 (简化为每用户一个主 key)"""

    PREFIX_USER = "session:user"
    PREFIX_EMAIL_VERIFY = "verify_email"

    def __init__(self):
        # 默认 24 小时过期；调用时可覆盖 expire
        super().__init__(namespace="user", default_expire=86400)

    # --------------------------------------------------
    # JWT 缓存
    # --------------------------------------------------

    async def cache_user_jwt(
        self,
        user_id: str,
        token: str,
        expire: Optional[int] = None,
    ) -> bool:
        """
        缓存用户 JWT
        key: session:user:{user_id}:jwt
        value: str (JWT)
        """
        key = f"{self.PREFIX_USER}:{user_id}:jwt"
        return await self.set(key, token, expire)

    async def get_user_jwt(self, user_id: str) -> Optional[str]:
        """获取用户 JWT"""
        key = f"{self.PREFIX_USER}:{user_id}:jwt"
        return await self.get(key)

    async def revoke_user_jwt(self, user_id: str) -> bool:
        """撤销用户 JWT"""
        key = f"{self.PREFIX_USER}:{user_id}:jwt"
        return (await self.delete(key)) > 0

    # --------------------------------------------------
    # 用户信息缓存
    # --------------------------------------------------

    async def cache_user_info(
        self,
        user_id: str,
        user_info: Dict[str, Any],
        expire: Optional[int] = None,
    ) -> bool:
        """
        缓存用户信息
        key: session:user:{user_id}:info
        value: dict
        """
        key = f"{self.PREFIX_USER}:{user_id}:info"
        data = {
            "id": user_id,
            **user_info,  # 不包含敏感字段
        }
        return await self.set(key, data, expire)

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        key = f"{self.PREFIX_USER}:{user_id}:info"
        data = await self.get(key)
        return data if isinstance(data, dict) else None

    # --------------------------------------------------
    # 组合逻辑：完整登录会话（JWT 包含用户信息）
    # --------------------------------------------------

    async def cache_user_session(
        self,
        user_id: str,
        token: str,
        user_info: Dict[str, Any],
        expire: Optional[int] = None,
    ) -> bool:
        """
        缓存完整用户会话：
        - JWT 内部包含用户信息（用于鉴权）
        - 用户信息单独缓存（用于资料查询）
        """
        # Step 1: 缓存 JWT
        jwt_ok = await self.cache_user_jwt(user_id, token, expire)
        if not jwt_ok:
            return False

        # Step 2: 缓存用户信息
        info_ok = await self.cache_user_info(user_id, user_info, expire)
        return jwt_ok and info_ok

    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取完整用户会话
        包含:
        {
            "jwt": str,
            "user": dict
        }
        """
        jwt_token = await self.get_user_jwt(user_id)
        user_info = await self.get_user_info(user_id)
        if not jwt_token and not user_info:
            return None
        return {"jwt": jwt_token, "user": user_info}

    # --------------------------------------------------
    # TTL 与存在性
    # --------------------------------------------------

    async def refresh_session_ttl(self, user_id: str, seconds: int) -> bool:
        """刷新 JWT 与用户信息 TTL"""
        keys = [
            f"{self.PREFIX_USER}:{user_id}:jwt",
            f"{self.PREFIX_USER}:{user_id}:info",
        ]
        results = [await self.expire(k, seconds) for k in keys]
        return all(results)

    async def exists_session(self, user_id: str) -> bool:
        """判断 JWT 或用户信息是否存在"""
        jwt_key = f"{self.PREFIX_USER}:{user_id}:jwt"
        info_key = f"{self.PREFIX_USER}:{user_id}:info"
        return await self.exists(jwt_key) or await self.exists(info_key)

    # --------------------------------------------------
    # 清理
    # --------------------------------------------------

    async def clear_user_cache(self, user_id: str) -> bool:
        """清理该用户的所有缓存项"""
        keys = [
            f"{self.PREFIX_USER}:{user_id}:jwt",
            f"{self.PREFIX_USER}:{user_id}:info",
            f"prefs:{user_id}",
        ]
        deleted = sum([await self.delete(k) for k in keys])
        return deleted > 0

    # --------------------------------------------------
    # 媒体库进入管理
    # --------------------------------------------------
    async def set_current_library(
        self, user_id: str, library: Dict[str, Any], expire: int = 86400
    ) -> bool:
        """设置用户当前进入的库"""
        key = f"{self.PREFIX_USER}:{user_id}:current_library"
        return await self.set(key, library, expire)

    async def get_current_library(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户当前库"""
        key = f"{self.PREFIX_USER}:{user_id}:current_library"
        data = await self.get(key)
        return data if isinstance(data, dict) else None

    async def delete_current_library(self, user_id: str) -> bool:
        """删除用户当前库缓存"""
        key = f"{self.PREFIX_USER}:{user_id}:current_library"
        return (await self.delete(key)) > 0

    PREFIX_DEVICE_SESSION = "session"

    async def add_device_session(
        self,
        user_id: str,
        session_id: str,
        token: str,
        device_info: Dict[str, Any],
        expire: Optional[int] = None,
    ) -> bool:
        detail_key = f"{self.PREFIX_USER}:{user_id}:{self.PREFIX_DEVICE_SESSION}:{session_id}"
        now_iso = datetime.now(timezone.utc).isoformat()
        rec = {
            "session_id": session_id,
            "token": token,
            "ip": device_info.get("ip"),
            "user_agent": device_info.get("user_agent"),
            "platform": device_info.get("platform"),
            "alias": device_info.get("alias"),
            "created_at": now_iso,
            "last_active_at": now_iso,
        }
        ok = await self.set(detail_key, rec, expire)
        if not ok:
            return False
        list_key = f"{self.PREFIX_USER}:{user_id}:sessions"
        lst = await self.get(list_key) or []
        summary = {k: rec[k] for k in ["session_id", "ip", "user_agent", "platform", "alias", "created_at", "last_active_at"]}
        lst = [s for s in lst if s.get("session_id") != session_id] + [summary]
        return await self.set(list_key, lst, expire)

    # --------------------------------------------------
    # 邮箱验证码缓存
    # --------------------------------------------------

    async def set_email_verify_code(
        self,
        email: str,
        code: str,
        expire: Optional[int] = 300,
    ) -> bool:
        """
        缓存邮箱验证码
        key: verify_email:{email}
        value: str (验证码)
        默认 5 分钟过期
        """
        key = f"{self.PREFIX_EMAIL_VERIFY}:{email}"
        return await self.set(key, code, expire)

    async def get_email_verify_code(self, email: str) -> Optional[str]:
        """获取邮箱验证码（未命中返回 None）"""
        key = f"{self.PREFIX_EMAIL_VERIFY}:{email}"
        val = await self.get(key)
        return str(val) if val is not None else None

    async def delete_email_verify_code(self, email: str) -> int:
        """删除邮箱验证码"""
        key = f"{self.PREFIX_EMAIL_VERIFY}:{email}"
        return await self.delete(key)

    async def get_device_session(self, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        detail_key = f"{self.PREFIX_USER}:{user_id}:{self.PREFIX_DEVICE_SESSION}:{session_id}"
        return await self.get(detail_key)

    async def list_device_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        list_key = f"{self.PREFIX_USER}:{user_id}:sessions"
        return (await self.get(list_key)) or []

    async def revoke_device_session(self, user_id: str, session_id: str) -> bool:
        detail_key = f"{self.PREFIX_USER}:{user_id}:{self.PREFIX_DEVICE_SESSION}:{session_id}"
        deleted = await self.delete(detail_key)
        list_key = f"{self.PREFIX_USER}:{user_id}:sessions"
        lst = await self.get(list_key) or []
        lst = [s for s in lst if s.get("session_id") != session_id]
        await self.set(list_key, lst)
        return deleted > 0

    async def revoke_all_sessions(self, user_id: str, except_session_id: Optional[str] = None) -> bool:
        # 选择性删除：保留 except_session_id 的细节记录
        ns_prefix = self._key(f"{self.PREFIX_USER}:{user_id}:{self.PREFIX_DEVICE_SESSION}:")
        keep_ns_key = self._key(f"{self.PREFIX_USER}:{user_id}:{self.PREFIX_DEVICE_SESSION}:{except_session_id}") if except_session_id else None
        deleted = 0
        async for raw_key in self.client.scan_iter(match=f"{ns_prefix}*"):
            if keep_ns_key and raw_key == keep_ns_key:
                continue
            res = await self.client.delete(raw_key)
            deleted += int(res or 0)

        list_key = f"{self.PREFIX_USER}:{user_id}:sessions"
        if except_session_id:
            kept = await self.get_device_session(user_id, except_session_id)
            summary = None
            if kept:
                summary = {k: kept.get(k) for k in ["session_id", "ip", "user_agent", "platform", "alias", "created_at", "last_active_at"]}
            await self.set(list_key, [summary] if summary else [])
        else:
            await self.set(list_key, [])
        return deleted > 0

    async def update_device_alias(self, user_id: str, session_id: str, alias: str) -> bool:
        detail_key = f"{self.PREFIX_USER}:{user_id}:{self.PREFIX_DEVICE_SESSION}:{session_id}"
        rec = await self.get(detail_key) or {}
        rec["alias"] = alias
        ok = await self.set(detail_key, rec)
        list_key = f"{self.PREFIX_USER}:{user_id}:sessions"
        lst = await self.get(list_key) or []
        for s in lst:
            if s.get("session_id") == session_id:
                s["alias"] = alias
        await self.set(list_key, lst)
        return ok

from typing import List
from src.core.handler import service_handler
from config.logging import get_service_logger
from src.models import UserRole
from src.routers.schemas.system import (
    HealthResponseSchema,
    StatusResponseSchema,
    VersionResponseSchema,
    ConfigPatchRequestSchema,
    ConfigPatchResponseSchema,
    LogQuerySchema,
    LogFetchResponse,
    LogType,
    ResourceUsageResponseSchema,
    UserActivityResponseSchema,
)
from src.logic.system.system_logic import SystemLogic

class SystemService:
    """
    系统服务层：权限校验、异常转换（业务异常）
    """

    def __init__(self) -> None:
        self.logic = SystemLogic()
        self.logger = get_service_logger("system_service")

    def _ensure_admin(self, current_user) -> None:
        if getattr(current_user, "role", None) != UserRole.ADMIN:
            from src.core.exceptions import ForbiddenError

            raise ForbiddenError("无权限")

    @service_handler(action="health_check")
    async def health_check(self) -> HealthResponseSchema:
        return await self.logic.health_check()

    @service_handler(action="status_monitor")
    async def status_monitor(self) -> StatusResponseSchema:
        return await self.logic.status_monitor()

    @service_handler(action="version_info")
    async def version_info(self) -> VersionResponseSchema:
        return await self.logic.version_info()

    @service_handler(action="patch_config")
    async def patch_config(
        self, data: ConfigPatchRequestSchema, current_user
    ) -> ConfigPatchResponseSchema:
        self._ensure_admin(current_user)
        return await self.logic.patch_config(data)

    @service_handler(action="get_logs")
    async def get_logs(self, data: LogQuerySchema, current_user) -> LogFetchResponse:
        self._ensure_admin(current_user)
        lines = await self.logic.get_logs(data.type, data.lines)
        return LogFetchResponse(log_type=data.type, lines=len(lines), content=lines)

    @service_handler(action="resource_usage")
    async def resource_usage(self, current_user) -> ResourceUsageResponseSchema:
        self._ensure_admin(current_user)
        return await self.logic.resource_usage()

    @service_handler(action="get_user_activities")
    async def get_user_activities(self, current_user) -> UserActivityResponseSchema:
        self._ensure_admin(current_user)
        return await self.logic.get_user_activities()

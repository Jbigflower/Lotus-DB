from pydantic import BaseModel, Field
from typing import Optional
from src.models import (
    SystemHealthStatus,
    SystemStatus,
    VersionInfo,
    ConfigPatchRequest,
    ConfigPatchResult,
    LogFetchResponse,
    LogType,
    ConfigCategory,
    ResourceUsage,
    UserActivity,
    UserActivityList,
)


class HealthResponseSchema(SystemHealthStatus):
    """健康检查响应模型"""

    pass


class StatusResponseSchema(SystemStatus):
    """系统状态响应模型"""

    pass


class VersionResponseSchema(VersionInfo):
    """版本信息响应模型"""

    pass


class ConfigPatchRequestSchema(ConfigPatchRequest):
    """配置修改请求模型（管理员）"""

    pass


class ConfigPatchResponseSchema(ConfigPatchResult):
    """配置修改响应模型"""

    pass


class LogQuerySchema(BaseModel):
    """日志查询请求模型（管理员）"""

    type: LogType = Field(..., description="日志类型")
    lines: int = Field(100, ge=1, le=2000, description="返回的最后 N 行")


class ResourceUsageResponseSchema(ResourceUsage):
    """资源占用响应模型"""
    pass


class UserActivitySchema(UserActivity):
    """用户活动记录"""
    pass


class UserActivityResponseSchema(UserActivityList):
    """用户活动列表响应"""
    pass

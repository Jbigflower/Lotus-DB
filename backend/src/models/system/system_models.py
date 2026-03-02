"""
系统状态与管理模型
"""

from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class LogType(str, Enum):
    app = "app"
    error = "error"
    performance = "performance"
    worker_all = "worker_all"
    worker_error = "worker_error"


class HealthCheckItem(BaseModel):
    name: str = Field(..., description="组件名称")
    status: str = Field(..., description="状态：ok/error")
    latency_ms: Optional[float] = Field(None, description="耗时 ms")
    details: Optional[Dict[str, str]] = Field(None, description="附加信息")
    message: Optional[str] = Field(None, description="错误信息")


class SystemHealthStatus(BaseModel):
    overall: str = Field(..., description="整体状态：ok/degraded/error")
    items: List[HealthCheckItem] = Field(
        default_factory=list, description="各组件健康项"
    )


class VersionInfo(BaseModel):
    app_name: str = Field(..., description="应用名称")
    app_version: str = Field(..., description="应用版本")
    environment: str = Field(..., description="运行环境")


class SystemStatus(BaseModel):
    timestamp: str = Field(..., description="时间戳")
    app: Dict[str, str] = Field(default_factory=dict, description="应用状态摘要")
    db: Dict[str, Dict] = Field(default_factory=dict, description="数据库/向量库状态")


class ConfigCategory(str, Enum):
    app = "app"
    database = "database"
    media = "media"
    llm = "llm"


class ConfigPatchRequest(BaseModel):
    category: ConfigCategory = Field(..., description="配置类别")
    updates: Dict[str, str] = Field(..., description="键值更新，形如 key->value")


class ConfigPatchResult(BaseModel):
    updated_keys: List[str] = Field(default_factory=list, description="更新的键列表")
    restart_required: bool = Field(True, description="是否需要重启以生效")
    preview: Dict[str, str] = Field(default_factory=dict, description="变更预览")


class LogFetchResponse(BaseModel):
    log_type: LogType = Field(..., description="日志类型")
    lines: int = Field(..., description="返回行数")
    content: List[str] = Field(default_factory=list, description="日志行内容")

class FolderUsage(BaseModel):
    path: str = Field(..., description="目录路径")
    exists: bool = Field(..., description="是否存在")
    size_bytes: int = Field(0, ge=0, description="目录总大小（字节）")
    file_count: int = Field(0, ge=0, description="文件数量")
    dir_count: int = Field(0, ge=0, description="子目录数量")

class ProcessUsage(BaseModel):
    cpu_percent: Optional[float] = Field(None, description="进程 CPU 百分比")
    memory_percent: Optional[float] = Field(None, description="进程内存占用百分比")
    memory_bytes: Optional[int] = Field(None, ge=0, description="进程内存占用（字节）")

class SystemUsage(BaseModel):
    cpu_percent: Optional[float] = Field(None, description="系统 CPU 百分比")
    memory_total: Optional[int] = Field(None, ge=0, description="系统内存总量（字节）")
    memory_used: Optional[int] = Field(None, ge=0, description="系统内存已用（字节）")
    memory_percent: Optional[float] = Field(None, description="系统内存占用百分比")

class ResourceUsage(BaseModel):
    timestamp: str = Field(..., description="时间戳")
    process: ProcessUsage = Field(default_factory=ProcessUsage, description="进程资源占用")
    system: SystemUsage = Field(default_factory=SystemUsage, description="系统资源占用")
    disk: Dict[str, FolderUsage] = Field(default_factory=dict, description="目录资源占用")


class UserActivity(BaseModel):
    username: str = Field(..., description="用户名")
    session_id: str = Field(..., description="会话ID")
    ip: Optional[str] = Field(None, description="IP地址")
    location: Optional[str] = Field(None, description="地理位置")
    device: Optional[str] = Field(None, description="设备名称/Agent")
    platform: Optional[str] = Field(None, description="平台/OS")
    login_at: Optional[str] = Field(None, description="登录时间")
    last_active_at: Optional[str] = Field(None, description="最后活跃时间")


class UserActivityList(BaseModel):
    items: List[UserActivity] = Field(default_factory=list, description="用户活动列表")

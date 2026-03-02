from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


# ===== Enums =====


class TaskType(str, Enum):
    """任务主类型"""

    IMPORT = "import"
    EXPORT = "export"
    BACKUP = "backup"
    ANALYSIS = "analysis"
    MAINTENANCE = "maintenance"
    DOWNLOAD = "download"
    OTHER = "other"


class TaskSubType(str, Enum):
    """任务子类型，与 worker 执行函数对齐"""

    # IMPORT
    # 批量导入电影
    MOVIE_IMPORT = "import_movies"

    # EXPORT

    # BACKUP

    # ANALYSIS
    # 提取元数据，图片、视频、音频、文档通用
    EXTRACT_METADATA = "extract_metadata"
    # 生成缩略图，雪碧图；适用于视频资产
    THUMB_SPRITE_GENERATE = "generate_thumb_sprite"
    # 同步外挂字幕
    SYNC_EXTERNAL_SUBTITLES = "sync_external_subtitles"

    # MAINTENANCE
    REFACTOR_LIBRARY_STRUCTURE = "refactor_library_structure"
    CLEANUP_LIBRARY_FILES = "cleanup_library_files"

    # DOWNLOAD
    DOWNLOAD_MOVIE_FILE = "download_movie_file"
    DOWNLOAD_ACTOR_FILE = "download_actor_file"
    DOWNLOAD_SUBTITLE_FILE = "download_subtitle_file"

    # OTHER
    # 写缓冲
    SYNC_DIRTY_COLLECTIONS = "sync_dirty_collections"
    REFRESH_COLLECTION_CACHE = "refresh_collection_cache"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    RETRYING = "retrying"


class TaskPriority(int, Enum):
    LOW = 0
    NORMAL = 20
    HIGH = 50
    URGENT = 100


# ===== Core Models =====


class ProgressInfo(BaseModel):
    """进度信息"""

    current_step: str = Field("", max_length=1000, description="当前执行步骤")
    total_steps: int = Field(0, min_value=0, description="总执行步骤数")
    completed_steps: int = Field(0, min_value=0, description="已完成执行步骤数")


class TaskBase(BaseModel):
    """基础任务字段"""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    task_type: TaskType = Field(..., description="任务主类型")
    sub_type: TaskSubType = Field(..., description="任务子类型")
    priority: TaskPriority = Field(TaskPriority.NORMAL, description="任务优先级")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    progress: ProgressInfo = Field(default_factory=ProgressInfo, description="任务进度")
    result: Dict[str, Any] = Field(default_factory=dict, description="任务结果")


class TaskInDB(TaskBase):
    """数据库模型"""

    id: str = Field(...)

    user_id: Optional[str] = None
    parent_task_id: Optional[str] = None  # 目前没有使用到

    error_message: Optional[str] = Field("", description="任务错误信息")
    error_details: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="任务错误详情"
    )

    # 执行控制
    scheduled_at: Optional[datetime] = None
    retry_count: int = Field(0, description="任务重试次数")
    max_retries: int = Field(3, description="任务最大重试次数")
    timeout_seconds: int = Field(3600, description="任务超时时间（秒）")

    # 时间信息
    created_at: datetime = Field(None)
    started_at: Optional[datetime] = Field(None)
    retry_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    updated_at: datetime = Field(None)

    class Config:
        json_schema_extra = {"example": {"name": "视频缩略图生成"}}


class TaskCreate(TaskBase):
    """任务创建模型"""

    user_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    max_retries: int = 3
    timeout_seconds: int = 3600
    scheduled_at: Optional[datetime] = None


class TaskUpdate(BaseModel):
    """任务更新模型"""

    status: Optional[TaskStatus] = None
    progress: Optional[ProgressInfo] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class TaskRead(TaskInDB):
    """前端响应模型"""

    pass


class TaskPageResult(BaseModel):
    items: List[TaskRead | TaskInDB]
    total: int
    page: int
    size: int
    pages: int

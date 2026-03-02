"""
Lotus-DB Models Package
统一导出所有模型类，提供便捷的导入接口
"""

# ===== 用户相关模型 =====
from .users.user_models import (
    UserRole,
    UserSettings,
    UserBase,
    UserCreate,
    UserUpdate,
    UserInDB,
    UserRead,
    UserPageResult,
)

from .users.user_asset_models import (
    UserAssetType,
    ClipMetadata,
    ScreenShotMetadata,
    UserAssetBase,
    UserAssetCreate,
    UserAssetUpdate,
    UserAssetRead,
    UserAssetInDB,
    UserAssetPageResult,
)

from .users.user_custom_list_models import (
    CustomListType,
    CustomListBase,
    CustomListCreate,
    CustomListUpdate,
    CustomListInDB,
    CustomListRead,
    CustomListPageResult,
)

from .users.watch_history_models import (
    WatchType,
    WatchHistoryBase,
    WatchHistoryCreate,
    WatchHistoryUpdate,
    WatchHistoryInDB,
    WatchHistoryRead,
    WatchHistoryPageResult,
)

# ===== 电影相关模型 =====
from .movies.movie_models import (
    MovieMetadata,
    MovieBase,
    MovieCreate,
    MovieUpdate,
    MovieInDB,
    MovieRead,
    MovieReadWithFlags,
    MoviePageResult,
)

from .movies.asset_models import (
    AssetType,
    AssetStoreType,
    AssetBase,
    AssetCreate,
    AssetUpdate,
    AssetInDB,
    AssetRead,
    AssetPageResult,
)

from .movies.library_models import (
    LibraryType,
    LibraryBase,
    LibraryInDB,
    LibraryCreate,
    LibraryUpdate,
    LibraryRead,
    LibraryPageResult,
)

# ===== 任务相关模型 =====
from .tasks.task_models import (
    TaskType,
    TaskSubType,
    TaskStatus,
    TaskPriority,
    ProgressInfo,
    TaskBase,
    TaskInDB,
    TaskCreate,
    TaskUpdate,
    TaskRead,
    TaskPageResult,
)

# ===== 系统模型 =====
from .system.system_models import (
    LogType,
    HealthCheckItem,
    SystemHealthStatus,
    VersionInfo,
    SystemStatus,
    ConfigCategory,
    ConfigPatchRequest,
    ConfigPatchResult,
    LogFetchResponse,
    ResourceUsage,
    SystemUsage,
    ProcessUsage,
    FolderUsage,
    UserActivity,
    UserActivityList,
)

# ===== 便捷别名 =====
# 为常用模型提供简短别名
NoteInDB = UserAssetInDB
NoteCreate = UserAssetCreate
NoteUpdate = UserAssetUpdate
NoteRead = UserAssetRead

from pydantic import BaseModel, Field
from typing import List


class PartialPageResult(BaseModel):
    """媒体库分页结果模型"""

    items: List = Field(default_factory=list, description="媒体库列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")


# ===== 导出列表 =====
__all__ = [
    "PartialPageResult",
    # 用户模型
    "UserRole",
    "UserSettings",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserInDB",
    "UserRead",
    "UserPageResult",
    # 用户资产模型
    "UserAssetType",
    "ClipMetadata",
    "ScreenShotMetadata",
    "UserAssetBase",
    "UserAssetCreate",
    "UserAssetUpdate",
    "UserAssetInDB",
    "UserAssetRead",
    "UserAssetPageResult",
    # 用户自定义列表模型
    "CustomListType",
    "CustomListBase",
    "CustomListCreate",
    "CustomListUpdate",
    "CustomListInDB",
    "CustomListRead",
    "CustomListPageResult",
    # 观看历史模型
    "WatchType",
    "WatchHistoryBase",
    "WatchHistoryCreate",
    "WatchHistoryUpdate",
    "WatchHistoryInDB",
    "WatchHistoryRead",
    "WatchHistoryPageResult",
    # 电影模型
    "MovieMetadata",
    "MovieBase",
    "MovieCreate",
    "MovieUpdate",
    "MovieInDB",
    "MovieRead",
    "MovieReadWithFlags",
    "MoviePageResult",
    # 资产模型
    "AssetType",
    "AssetBase",
    "AssetCreate",
    "AssetUpdate",
    "AssetInDB",
    "AssetRead",
    "AssetPageResult",
    "AssetStoreType",
    # 媒体库模型
    "LibraryType",
    "LibraryBase",
    "LibraryInDB",
    "LibraryCreate",
    "LibraryUpdate",
    "LibraryRead",
    "LibraryPageResult",
    # 任务模型
    "TaskType",
    "TaskSubType",
    "TaskStatus",
    "TaskPriority",
    "ProgressInfo",
    "TaskBase",
    "TaskInDB",
    "TaskCreate",
    "TaskUpdate",
    "TaskRead",
    "TaskPageResult",
    # 系统模型
    "LogType",
    "HealthCheckItem",
    "SystemHealthStatus",
    "VersionInfo",
    "SystemStatus",
    "ConfigCategory",
    "ConfigPatchRequest",
    "ConfigPatchResult",
    "LogFetchResponse",
    "ResourceUsage",
    "SystemUsage",
    "ProcessUsage",
    "FolderUsage",
    "UserActivity",
    "UserActivityList",
    # 便捷别名
    "NoteInDB",
    "NoteCreate",
    "NoteUpdate",
    "NoteRead",
]

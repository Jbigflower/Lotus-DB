# src/services/__init__.py
"""
服务层模块导入
提供统一的服务层接口，包括电影、用户、同步等相关服务
"""

# 电影相关服务
from .movies.asset_service import MovieAssetService
from .movies.library_service import LibraryService
from .movies.movie_service import MovieService

# 用户相关服务
from .users.asset_service import AssetService
from .users.auth_service import AuthService
from .users.collection_service import CollectionService
from .users.user_service import UserService

# 任务相关服务
from .tasks.task_service import TaskService

# 同步相关服务
from .sync.base_sync_service import BaseSyncService
from .sync.memory_sync_service import MemorySyncService
from .sync.movie_sync_service import MovieSyncService
from .sync.note_sync_service import NoteSyncService

# 搜索相关服务
from .search.search_service import SearchService
from .search.rag_service import RagSearchService

__all__ = [
    # 电影相关服务
    "MovieAssetService",
    "LibraryService",
    "MovieService",
    # 用户相关服务
    "AssetService",
    "AuthService",
    "CollectionService",
    "UserService",
    # 任务相关服务
    "TaskService",
    # 同步相关服务
    "BaseSyncService",
    "MemorySyncService",
    "MovieSyncService",
    "NoteSyncService",
    # 搜索相关服务
    "SearchService",
    "RagSearchService",
]

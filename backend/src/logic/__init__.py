# src/logic/__init__.py
"""
Logic层模块导出
提供业务逻辑处理类的统一导入接口
"""

# Movies Logic
from .movies.asset_logic import MovieAssetLogic
from .movies.library_logic import LibraryLogic
from .movies.movie_logic import MovieLogic

# Task Logic
from .task.task_logic import TaskLogic

# Users Logic
from .users.auth_logic import AuthLogic
from .users.collection_logic import CollectionLogic
from .users.user_asset_logic import UserAssetLogic
from .users.user_logic import UserLogic
from .users.watch_history_logic import WatchHistoryLogic

__all__ = [
    # Movies
    "MovieAssetLogic",
    "LibraryLogic",
    "MovieLogic",
    # Task
    "TaskLogic",
    # Users
    "AuthLogic",
    "CollectionLogic",
    "UserAssetLogic",
    "UserLogic",
    "WatchHistoryLogic",
]

"""
MongoDB Repository Layer
提供基于 MongoDB 的数据访问层实现
"""

from src.repos.mongo_repos.base_repo import BaseRepo
from src.repos.mongo_repos.movies.asset_repo import AssetRepo
from src.repos.mongo_repos.movies.library_repo import LibraryRepo
from src.repos.mongo_repos.movies.movie_repo import MovieRepo
from src.repos.mongo_repos.users.user_asset_repo import UserAssetRepo
from src.repos.mongo_repos.users.user_custom_list_repo import UserCustomListRepo
from src.repos.mongo_repos.users.user_repo import UserRepo
from src.repos.mongo_repos.users.watch_history_repo import WatchHistoryRepo
from src.repos.mongo_repos.task.task_repo import TaskRepo

__all__ = [
    "BaseRepo",
    "MovieRepo",
    "AssetRepo",
    "LibraryRepo",
    "UserRepo",
    "UserCustomListRepo",
    "UserAssetRepo",
    "WatchHistoryRepo",
    "TaskRepo",
]

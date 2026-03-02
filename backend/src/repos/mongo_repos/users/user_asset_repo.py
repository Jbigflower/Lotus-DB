"""
用户个人创作内容仓储层
提供用户生成内容（笔记、截图、剪辑、影评等）的数据访问和业务逻辑
支持文本资产和媒体资产的分离管理
"""
from bson import ObjectId
from typing import List, Optional, Dict, Any, Type
from motor.motor_asyncio import AsyncIOMotorClientSession
from pymongo import UpdateOne # Bulk-write
from pymongo.errors import DuplicateKeyError, PyMongoError
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import (
    UserAssetType,
    ClipMetadata,
    ScreenShotMetadata,
    UserAssetBase,
    UserAssetCreate,
    UserAssetUpdate,
    UserAssetInDB,
    UserAssetRead,
    UserAssetPageResult,
    PartialPageResult,
)
from config.logging import get_repo_logger
from src.core.handler import repo_handler
from src.core.exceptions import BaseRepoException

logger = get_repo_logger("user_asset_repo")


class UserAssetRepo(BaseRepo):
    """用户资产仓储实体类：仅保留数据转换的抽象方法实现"""

    def __init__(self):
        super().__init__(
            collection_name="user_assets",
            InDB_Model=UserAssetInDB,
            Create_Model=UserAssetCreate,
            Update_Model=UserAssetUpdate,
            soft_delete=True,
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[UserAssetCreate]) -> List[Dict[str, Any]]:
        """
        将 Pydantic 模型转换为字典列表，用于批量操作
        """
        docs = super().convert_createModel_to_dict(models)
        for doc in docs:
            if "user_id" in doc and doc["user_id"]:
                doc["user_id"] = ObjectId(doc["user_id"])
            if "movie_id" in doc and doc["movie_id"]:
                doc["movie_id"] = ObjectId(doc["movie_id"])
            if "related_movie_ids" in doc and doc["related_movie_ids"]:
                doc["related_movie_ids"] = [ObjectId(id) for id in doc["related_movie_ids"]]
        return docs

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[UserAssetInDB]:
        """
        将 MongoDB 文档转换为 Pydantic 模型列表
        """
        for doc in docs:
            if "user_id" in doc:
                doc["user_id"] = str(doc["user_id"])
            if "related_movie_ids" in doc:
                doc["related_movie_ids"] = [str(id) for id in doc["related_movie_ids"]]
            if "movie_id" in doc:
                doc["movie_id"] = str(doc["movie_id"])
        return super().convert_dict_to_pydanticModel(docs)

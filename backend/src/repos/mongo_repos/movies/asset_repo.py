"""
资源管理仓储层
提供媒体资源相关的数据访问和业务逻辑
"""
from bson import ObjectId
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClientSession
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import (
    AssetInDB,
    AssetCreate,
    AssetUpdate,
    AssetRead,
    AssetPageResult,
    AssetType,
    PartialPageResult,  # 新增：支持投影分页返回
)
from config.logging import get_repo_logger
from src.core.handler import repo_handler

logger = get_repo_logger("asset_repo")


class AssetRepo(BaseRepo[AssetInDB, AssetCreate, AssetUpdate]):
    """资源仓储类"""

    def __init__(self):
        super().__init__(
            collection_name="assets",
            InDB_Model=AssetInDB,
            Create_Model=AssetCreate,
            Update_Model=AssetUpdate,
            soft_delete=True,
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[AssetCreate]) -> List[Dict[str, Any]]:
        docs = super().convert_createModel_to_dict(models)
        for doc in docs:
            if "library_id" in doc:
                doc["library_id"] = ObjectId(doc["library_id"])
            if "movie_id" in doc and doc["movie_id"]:
                doc["movie_id"] = ObjectId(doc["movie_id"])
        return docs

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[AssetInDB]:
        """
        将 MongoDB 文档转换为 Pydantic 模型列表
        """
        for doc in docs:
            if "library_id" in doc:
                doc["library_id"] = str(doc["library_id"])
            if "movie_id" in doc:
                doc["movie_id"] = str(doc["movie_id"])
        return super().convert_dict_to_pydanticModel(docs)
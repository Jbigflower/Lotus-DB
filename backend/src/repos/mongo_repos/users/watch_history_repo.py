"""
观看历史仓储层（精简版）

仅作为 BaseRepo 的实体类，保留抽象方法实现：
- convert_createModel_to_dict
- convert_dict_to_pydanticModel
"""
from bson import ObjectId
from typing import List, Dict, Any
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import (
    WatchHistoryInDB,
    WatchHistoryCreate,
    WatchHistoryUpdate,
)


class WatchHistoryRepo(
    BaseRepo[WatchHistoryInDB, WatchHistoryCreate, WatchHistoryUpdate]
):
    """观看历史仓储类（仅保留必要的抽象方法实现）"""

    def __init__(self):
        super().__init__(
            collection_name="watch_histories",
            InDB_Model=WatchHistoryInDB,
            Create_Model=WatchHistoryCreate,
            Update_Model=WatchHistoryUpdate,
            soft_delete=False,
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[WatchHistoryCreate]) -> List[Dict[str, Any]]:
        """
        将 Pydantic 模型转换为字典列表，用于批量操作
        """
        docs = super().convert_createModel_to_dict(models)
        # 处理 ObjectId 字段
        for doc in docs:
            if "user_id" in doc and isinstance(doc["user_id"], str):
                doc["user_id"] = ObjectId(doc["user_id"])
            if "movie_id" in doc and isinstance(doc["movie_id"], str):
                doc["movie_id"] = ObjectId(doc["movie_id"])
            if "asset_id" in doc and isinstance(doc["asset_id"], str):
                doc["asset_id"] = ObjectId(doc["asset_id"])
        return docs

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[WatchHistoryInDB]:
        """
        将 MongoDB 文档转换为 Pydantic 模型列表
        """
        for doc in docs:
            if "user_id" in doc:
                doc["user_id"] = str(doc["user_id"])
            if "movie_id" in doc:
                doc["movie_id"] = str(doc["movie_id"])
            if "asset_id" in doc:
                doc["asset_id"] = str(doc["asset_id"])
        return super().convert_dict_to_pydanticModel(docs)

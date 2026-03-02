"""
用户自定义片单仓储层
提供用户片单相关的数据访问和业务逻辑
"""
from bson import ObjectId
from typing import List, Optional, Dict, Any, Union
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import (
    CustomListInDB,
    CustomListCreate,
    CustomListUpdate,
)


class UserCustomListRepo(BaseRepo[CustomListInDB, CustomListCreate, CustomListUpdate]):
    """用户自定义片单仓储类（简化为实体类，仅保留抽象方法实现）"""

    def __init__(self):
        super().__init__(
            collection_name="user_custom_lists",
            InDB_Model=CustomListInDB,
            Create_Model=CustomListCreate,
            Update_Model=CustomListUpdate,
            soft_delete=False,
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[CustomListCreate]) -> List[Dict[str, Any]]:
        docs = super().convert_createModel_to_dict(models)
        for doc in docs:
            if "user_id" in doc:
                doc["user_id"] = ObjectId(doc["user_id"])
            if "movies" in doc and doc["movies"]:
                doc["movies"] = [ObjectId(id) for id in doc["movies"]]
        return docs

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[CustomListInDB]:
        for doc in docs:
            if "user_id" in doc:
                doc["user_id"] = str(doc["user_id"])
            if "movies" in doc and doc["movies"]:
                doc["movies"] = [str(id) for id in doc["movies"]]
        return super().convert_dict_to_pydanticModel(docs)
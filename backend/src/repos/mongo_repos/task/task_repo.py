"""
任务管理仓储层（精简版）

仅作为 BaseRepo 的实体类，保留抽象方法实现：
- convert_createModel_to_dict
- convert_dict_to_pydanticModel
"""
from bson import ObjectId
from typing import List, Dict, Any
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import TaskInDB, TaskCreate, TaskUpdate


class TaskRepo(BaseRepo[TaskInDB, TaskCreate, TaskUpdate]):
    """任务仓储类（仅保留必要的抽象方法实现）"""

    def __init__(self):
        super().__init__(
            collection_name="tasks",
            InDB_Model=TaskInDB,
            Create_Model=TaskCreate,
            Update_Model=TaskUpdate,
            soft_delete=True,
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[TaskCreate]) -> List[Dict[str, Any]]:
        """
        将 Pydantic 模型转换为字典列表，用于批量操作
        """
        docs = super().convert_createModel_to_dict(models)
        for doc in docs:
            if "user_id" in doc and isinstance(doc["user_id"], str):
                doc["user_id"] = ObjectId(doc["user_id"])
        return docs

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[TaskInDB]:
        """
        将 MongoDB 文档转换为 Pydantic 模型列表
        """
        for doc in docs:
            if "user_id" in doc:
                doc["user_id"] = str(doc["user_id"])
        return super().convert_dict_to_pydanticModel(docs)

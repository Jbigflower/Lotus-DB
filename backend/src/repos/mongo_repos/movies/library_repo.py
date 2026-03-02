"""
媒体库配置仓储层
提供媒体库相关的数据访问和业务逻辑
"""
from bson import ObjectId
from typing import List, Dict, Any
from src.models import (
    LibraryInDB,
    LibraryCreate,
    LibraryUpdate,
)
from src.repos.mongo_repos.base_repo import BaseRepo



class LibraryRepo(BaseRepo[LibraryInDB, LibraryCreate, LibraryUpdate]):
    """媒体库仓储类"""

    def __init__(self):
        super().__init__(
            collection_name="libraries",
            InDB_Model=LibraryInDB,
            Create_Model=LibraryCreate,
            Update_Model=LibraryUpdate,
            soft_delete=True,
        )
    
    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[LibraryCreate]) -> List[Dict[str, Any]]:
        """
        将 Pydantic 模型转换为字典列表，用于批量操作
        """
        library_dicts = super().convert_createModel_to_dict(models)
        for library_dict in library_dicts:
            if "user_id" in library_dict:
                library_dict["user_id"] = ObjectId(library_dict["user_id"])
        return library_dicts

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[LibraryInDB]:
        """
        将 MongoDB 文档转换为 Pydantic 模型列表
        """
        for doc in docs:
            if "user_id" in doc:
                doc["user_id"] = str(doc["user_id"])
        return super().convert_dict_to_pydanticModel(docs)
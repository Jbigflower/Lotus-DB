from typing import List, Optional, Dict, Any, Tuple
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import (
    UserInDB,
    UserCreate,
    UserUpdate,
)


class UserRepo(BaseRepo[UserInDB, UserCreate, UserUpdate]):
    """用户仓储类"""

    def __init__(self):
        super().__init__(
            collection_name="users",
            InDB_Model=UserInDB,
            Create_Model=UserCreate,
            Update_Model=UserUpdate,
            soft_delete=False,  # 用户不支持软删
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[UserCreate]) -> List[Dict[str, Any]]:
        return super().convert_createModel_to_dict(models)

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[UserInDB]:
        return super().convert_dict_to_pydanticModel(docs)
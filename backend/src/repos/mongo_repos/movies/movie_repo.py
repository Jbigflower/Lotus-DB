"""
电影元数据仓储层
提供电影相关的数据访问和业务逻辑
"""
from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from src.repos.mongo_repos.base_repo import BaseRepo
from src.models import MovieInDB, MovieCreate, MovieUpdate


class MovieRepo(BaseRepo[MovieInDB, MovieCreate, MovieUpdate]):
    """电影仓储类"""

    def __init__(self):
        super().__init__(
            collection_name="movies",
            InDB_Model=MovieInDB,
            Create_Model=MovieCreate,
            Update_Model=MovieUpdate,
            soft_delete=True,
        )

    # -------------------------------------- 抽象函数实现 --------------------------------------
    def convert_createModel_to_dict(self, models: List[MovieCreate]) -> List[Dict[str, Any]]:
        """
        将 Pydantic 模型转换为字典列表，用于批量操作
        """
        docs = super().convert_createModel_to_dict(models)
        # 处理 library_id 字段
        for doc in docs:
            if "library_id" in doc:
                doc["library_id"] = ObjectId(doc["library_id"])
            if "release_date" in doc and doc["release_date"]:
                doc["release_date"] = doc["release_date"].isoformat()
        return docs

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[MovieInDB]:
        """
        将 MongoDB 文档转换为 Pydantic 模型列表
        """
        for doc in docs:
            if "library_id" in doc:
                doc["library_id"] = str(doc["library_id"])
            if "release_date" in doc and doc["release_date"]:
                if isinstance(doc["release_date"], str):
                    try:
                        doc["release_date"] = datetime.strptime(doc["release_date"], "%Y-%m-%d").date()
                    except ValueError:
                        # Fallback or ignore if format doesn't match
                        pass
                elif isinstance(doc["release_date"], datetime):
                    doc["release_date"] = doc["release_date"].date()
        return super().convert_dict_to_pydanticModel(docs)

    # -------------------------------------- 父类特定方法修改 --------------------------------------
    async def update_many(
        self,
        filter_query: Dict[str, Any],
        update_payload: Dict[str, Any],
        session = None,
        *,
        fetch_after_update: bool = True,
        affect_ids: Optional[List[str]] = None
    ):
        """
        批量更新文档
        :param fetch_after_update: 是否在更新后重新查询文档，默认 True，方便更新缓存，确保一致性
        :param affect_ids: 待更新的文档id，加速 *_by_ids 特化方法
        """
        if "release_date" in update_payload and update_payload["release_date"]:
            update_payload["release_date"] = update_payload["release_date"].isoformat()
        
        return await super().update_many(
            filter_query,
            update_payload,
            session,
            fetch_after_update=fetch_after_update,
            affect_ids=affect_ids
        )
    
    async def update_one(
        self,
        filter_query: Dict[str, Any],
        update_payload: Dict[str, Any],
        session = None,
    ):
        """
        更新单个文档 - 使用 find-one-and-update 方法 优化处理速率
        """
        if "release_date" in update_payload and update_payload["release_date"]:
            update_payload["release_date"] = update_payload["release_date"].isoformat()

        return await super().update_one(
            filter_query,
            update_payload,
            session,
        )
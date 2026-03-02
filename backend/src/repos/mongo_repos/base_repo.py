"""
MongoDB 基础仓储类

提供统一的 CRUD 操作接口，采用批量优先的设计理念：
- 批量操作作为核心实现
- 单个操作通过调用批量操作实现
- 便捷函数提供
- 软删除支持
- 数据转换约束（Pydantic ↔ MongoDB），需要继承类实现
- 事务支持
- 统一异常处理和日志记录
"""

from abc import ABC, abstractmethod
from bson import ObjectId
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union, Set

# 数据库连接
from src.db.mongo_db import get_mongo_manager
from contextlib import asynccontextmanager # 事务支持
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorClientSession
from pymongo import UpdateOne # Bulk-write

# 异常处理
from pymongo.errors import DuplicateKeyError, PyMongoError, BulkWriteError
from pydantic import BaseModel, ValidationError as PydanticValidationError
from src.core.exceptions import RepoValidationError, BaseRepoException, DuplicateDocumentError

# 日志配置
from config.logging import get_repo_logger
from src.core.handler import repo_handler

# 
from config.setting import get_settings

settings = get_settings()


ModelInDB = TypeVar("ModelInDB", bound=BaseModel)
ModelCreate = TypeVar("ModelCreate", bound=BaseModel)
ModelUpdate = TypeVar("ModelUpdate", bound=BaseModel)


class BaseRepo(Generic[ModelInDB, ModelCreate, ModelUpdate], ABC):
    """MongoDB 基础仓储类 - 批量优先设计"""

    MAX_FIND_LIMIT = settings.performance.max_query_limit
    MAX_BATCH_LIMIT = settings.performance.max_batch_size

    def __init__(
        self,
        collection_name: str,
        InDB_Model: Type[ModelInDB],
        Create_Model: Type[ModelCreate],
        Update_Model: Type[ModelUpdate],
        soft_delete: bool = True,
    ):
        """
        初始化基础仓储
            collection_name: MongoDB 集合名称
            InDB_Model: Pydantic 模型类
            Create_Model: Pydantic 创建模型类
            Update_Model: Pydantic 更新模型类
        """
        self.collection_name = collection_name
        self._collection: Optional[AsyncIOMotorCollection] = None
        self.InDB_Model = InDB_Model
        self.Create_Model = Create_Model
        self.Update_Model = Update_Model
        self.soft_delete = soft_delete
        self.logger = get_repo_logger(self.collection_name)
        self._allow_fields: Set[str] = set(self.InDB_Model.model_fields.keys()) | {"_id"}

    @property
    def collection(self) -> AsyncIOMotorCollection:
        """获取 MongoDB 集合"""
        if self._collection is None:
            self._collection = get_mongo_manager().get_collection(self.collection_name)
            self.logger.info(f"初始化仓储 {self.collection_name}")
        return self._collection

    # -------------------------------------- 数据处理 环节 --------------------------------------

    @abstractmethod
    def convert_createModel_to_dict(self, models: List[ModelCreate]) -> List[Dict[str, Any]]:
        """
        将 Pydantic 模型实例转换为 MongoDB 文档字典
        1）批量添加：created_at、updated_at 字段
        2) 批量添加：is_deleted、deleted_at 字段（需要开启软删除）
        ……
        """
        # 转换为字典列表
        try:
            models_dict = [doc.model_dump() for doc in models]
        except AttributeError as e:
            raise RepoValidationError(f"{self.collection_name}: 传入的文档对象并非 Pydantic 对象，缺少 model_dump 方法: {e}") from e

        # 添加时间戳
        now = datetime.now(timezone.utc)
        for doc in models_dict:
            doc["created_at"] = now
            doc["updated_at"] = now
            if self.soft_delete:
                doc["is_deleted"] = False
                doc["deleted_at"] = None

        return models_dict

    @abstractmethod
    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[ModelInDB]:
        """
        将 MongoDB 文档字典转换为 Pydantic 模型实例
        1）自动处理 _id -> id
        ……
        """
        if not docs:
            return []

        if "_id" in docs[0]:
            for doc in docs:
                doc["id"] = str(doc.pop("_id"))

        return [self.InDB_Model(**doc) for doc in docs]


    # -------------------------------------- CRUD 批处理环节 --------------------------------------
    @repo_handler("批量插入文档")
    async def insert_many(
        self,
        docs: List[ModelCreate],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> List[ModelInDB]:
        """
        批量插入文档
        """
        if not docs:
            return []

        # 转换为字典列表
        docs_dict = self.convert_createModel_to_dict(docs)

        try:
            # 批量插入文档
            result = await self.collection.insert_many(
                docs_dict,
                session=session
            )
        except BulkWriteError as e:
            # 提取重复键信息
            errmsg = str(e)
            dup_key_info = ""
            if "dup key:" in errmsg:
                start = errmsg.find("dup key:") + len("dup key:")
                dup_key_info = errmsg[start:].strip()
            raise DuplicateDocumentError(
                f"{self.collection_name}: 文档重复，重复键信息: {dup_key_info}"
            ) from e

        # 转换为模型实例，自动处理 _id -> id
        inserted_ids = result.inserted_ids
        for doc in docs_dict:
            doc["id"] = str(inserted_ids.pop(0))

        try:
            return self.convert_dict_to_pydanticModel(docs_dict)
        except PydanticValidationError as e:
            raise RepoValidationError(f"{self.collection_name}: 库字段 映射到 模型字段失败: {e}") from e

    @repo_handler("批量查找文档")
    async def find(
        self,
        filter_query: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 1000,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, int]] = None,
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> List[Union[ModelInDB, Dict[str, Any]]]:
        """
        查找多个文档
        基于 _id 的分页，需要调用方手动拼接 filter_dict 中的 _id 条件 并在 sort 中添加 (_id, 1) 或 (_id, -1)
        注意：基于 _id 的分页请确保，当前集合中 存在 sort && -id 的复式索引，否则性能可能会受到影响
        或者，也可以采用其他符合 唯一性的 复式索引 的 字段 替代 _id 字段
        """
        if limit > self.MAX_FIND_LIMIT:
            raise RepoValidationError(f"{self.collection_name}: 查找文档数量超过上限 {self.MAX_FIND_LIMIT}")

        # 检查 projection 字段是否合法
        if projection:
            invalid_fields = set(projection.keys()) - self._allow_fields
            if invalid_fields:
                raise RepoValidationError(f"{self.collection_name}: 查找文档 projection 字段不合法: {invalid_fields}")

        cursor = self.collection.find(filter_query, projection=projection, session=session)
        if skip > 0:
            cursor.skip(skip)
        if limit > 0:
            cursor.limit(limit)
        if sort:
            cursor.sort(sort)
        docs = await cursor.to_list(length=limit)

        return docs if projection else self.convert_dict_to_pydanticModel(docs)

    @repo_handler("批量更新文档")
    async def update_many(
        self,
        filter_query: Dict[str, Any],
        update_payload: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
        *,
        fetch_after_update: bool = True,
        affect_ids: Optional[List[str]] = None
    ) -> Union[int, List[ModelInDB]]:
        """
        批量更新文档
        :param fetch_after_update: 是否在更新后重新查询文档，默认 True，方便更新缓存，确保一致性
        :param affect_ids: 待更新的文档id，加速 *_by_ids 特化方法
        """
        if fetch_after_update and affect_ids is None:
            docs_to_update = await self.collection.find(
                    filter_query, session=session   
                ).to_list(length=None)
            affect_ids = [doc["_id"] for doc in docs_to_update]
        
            if not affect_ids:
                return []
        
        result = await self.collection.update_many(filter_query, {"$set": update_payload}, session=session)
        
        if fetch_after_update and result.modified_count > 0:
            if isinstance(affect_ids[0], str):
                affect_ids = [ObjectId(id) for id in affect_ids]

            updated_docs = await self.collection.find({"_id": {"$in": affect_ids}}, session=session).to_list(length=None)
            return self.convert_dict_to_pydanticModel(updated_docs)

        return result.modified_count

    @repo_handler("批量删除文档")
    async def delete_many(
        self,
        filter_query: Dict[str, Any],
        soft_delete: bool = True,
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> int:
        """
        批量删除文档
        :param soft_delete: 是否软删除，默认 True，将文档的 is_deleted 字段设置为 True
        """
        if soft_delete and self.soft_delete:
            now = datetime.now(timezone.utc)
            filter_query["is_deleted"] = False
            update_doc = {"is_deleted": True, "deleted_at": now, "updated_at": now}
            result = await self.collection.update_many(filter_query, {"$set": update_doc}, session=session)
            return result.modified_count

        elif soft_delete and not self.soft_delete:
            raise BaseRepoException(f"{self.collection_name}:当前类未开启软删除模式，无法执行批量软删除操作")

        else:
            result = await self.collection.delete_many(filter_query, session=session)
            return result.deleted_count        

    @repo_handler("批量恢复文档")
    async def restore_many(
        self,
        filter_query: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
        *,
        fetch_after_restore: bool = True,
        affect_ids: Optional[List[str]] = None
    ) -> Union[int, List[ModelInDB]]:
        """
        批量恢复文档，复用 update-many
        :param fetch_after_restore: 是否在恢复后重新查询文档，默认 True，方便更新缓存，确保一致性
        :param affect_ids: 待恢复的文档id，加速 *_by_ids 特化方法
        """
        if self.soft_delete is False:
            raise BaseRepoException("当前类未开启软删除模式，无法恢复文档")

        filter_query["is_deleted"] = True
        update_doc = {
                "is_deleted": False,
                "deleted_at": None,
                "updated_at": datetime.now(timezone.utc),
            }

        return self.update_many(
            filter_query,
            update_doc,
            session=session,
            fetch_after_update=fetch_after_restore,
            affect_ids=affect_ids,
        )

    # -------------------------------------- CRUD 单例环节 --------------------------------------
    @repo_handler("插入单个文档")
    async def insert_one(
        self,
        doc: ModelCreate,
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> ModelInDB:
        """
        插入单个文档 - 通过调用批量插入实现
        """
        inserted = await self.insert_many([doc], session=session)
        return inserted[0]

    @repo_handler("更新单个文档")
    async def update_one(
        self,
        filter_query: Dict[str, Any],
        update_payload: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> Optional[ModelInDB]:
        """
        更新单个文档 - 使用 find-one-and-update 方法 优化处理速率
        """
        if not isinstance(update_payload, dict):
            raise BaseRepoException("更新payload必须为字典类型")
        result = await self.collection.find_one_and_update(
            filter_query, {"$set": update_payload}, session=session, return_document=True
        )
        return self.convert_dict_to_pydanticModel([result])[0] if result else None

    @repo_handler("删除单个文档")
    async def delete_one(
        self,
        filter_query: Dict[str, Any],
        soft_delete: bool = True,
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> Optional[ModelInDB]:
        """
        删除单个文档 - 使用 find-one-and-update 方法 优化处理速率
        """
        if soft_delete and self.soft_delete:
            now = datetime.now(timezone.utc)
            filter_query["is_deleted"] = False
            update_doc = {"is_deleted": True, "deleted_at": now, "updated_at": now}
            result = await self.collection.find_one_and_update(
                filter_query, {"$set": update_doc}, session=session, return_document=True
            )
            return self.convert_dict_to_pydanticModel([result])[0] if result else None

        elif soft_delete and not self.soft_delete:
            raise BaseRepoException(f"{self.collection_name}:当前类未开启软删除模式，无法执行软删除操作")

        else:
            result = await self.collection.find_one_and_delete(filter_query, session=session)
            return self.convert_dict_to_pydanticModel([result])[0] if result else None
    
    @repo_handler("恢复单个文档")
    async def restore_one(
        self,
        filter_query: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> Optional[ModelInDB]:
        """
        恢复单个文档 - 使用 find-one-and-update 方法 优化处理速率
        """
        if self.soft_delete is False:
            raise BaseRepoException("当前类未开启软删除模式，无法恢复文档")

        filter_query["is_deleted"] = True
        update_doc = {
                "is_deleted": False,
                "deleted_at": None,
                "updated_at": datetime.now(timezone.utc),
            }
        return await self.update_one(filter_query, update_doc, session=session)
         
    # -------------------------------------- 热门函数 --------------------------------------
    async def find_by_ids(
        self, doc_ids: List[str], session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[List[ModelInDB]]:
        """根据ID列表查找文档"""
        if not doc_ids:
            return []
        ids = [ObjectId(_id) for _id in doc_ids]
        if len(ids) == 1:
            result = await self.find({"_id": ids[0]}, session=session)
            return result if result else []

        return await self.find({"_id": {"$in": ids}}, session=session)

    async def update_by_ids(
        self, ids: List[str], update_payload: Dict[str, Any], session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[List[ModelInDB]]:
        """根据ID列表批量更新文档"""
        if not ids:
            return []
        ids = [ObjectId(id) for id in ids]
        if len(ids) == 1:
            result = await self.update_one({"_id": ids[0]}, update_payload, session=session)
            return [result] if result else []
        else:
            return await self.update_many(
                {"_id": {"$in": ids}},
                update_payload,
                session=session,
                fetch_after_update=True,
                affect_ids=ids
            )

    async def delete_by_ids(
        self, ids: List[str], soft_delete: bool = True, session: Optional[AsyncIOMotorClientSession] = None
    ) -> int:
        """根据ID列表批量删除文档"""
        if not ids:
            return 0
        ids = [ObjectId(id) for id in ids]
        if len(ids) == 1:
            return await self.delete_many({"_id": ids[0]}, soft_delete, session=session)
        else:
            return await self.delete_many(
                {"_id": {"$in": ids}},
                soft_delete,
                session=session,
            )

    async def restore_by_ids(
        self, ids: List[str], session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[List[ModelInDB]]:
        """根据ID列表批量恢复文档"""
        if not ids:
            return True
        ids = [ObjectId(id) for id in ids]
        if len(ids) == 1:
            result = await self.restore_one({"_id": ids[0]}, session=session)
            return [result] if result else []
        else:
            return await self.restore_many(
                {"_id": {"$in": ids}},
                session=session,
                fetch_after_restore=True,
                affect_ids=ids,
            )

    async def find_by_id(
        self, doc_id: str, session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[ModelInDB]:
        """根据ID查找文档"""
        if not doc_id:
            return None
        id = ObjectId(doc_id)
        result = await self.find({"_id": id}, session=session)
        return result[0] if result else None


    async def update_by_id(
        self, doc_id: str, update_payload: Dict[str, Any], session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[ModelInDB]:
        """根据ID更新文档"""
        if not doc_id:
            return None
        id = ObjectId(doc_id)
        return await self.update_one({"_id": id}, update_payload, session=session)
        

    async def delete_by_id(
        self, doc_id: str, soft_delete: bool = True, session: Optional[AsyncIOMotorClientSession] = None
    ) -> int:
        """根据ID删除文档"""
        if not doc_id:
            return 0
        id = ObjectId(doc_id)
        return await self.delete_many({"_id": id}, soft_delete, session=session)

    async def restore_by_id(
        self, doc_id: str, session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[ModelInDB]:
        """根据ID恢复文档"""
        if not doc_id:
            return None
        id = ObjectId(doc_id)
        result = await self.restore_one({"_id": id}, session=session)
        return result if result else None

    # -------------------------------------- 通用数据操作增强 --------------------------------------
    @repo_handler("统计文档数量")
    async def count(
        self,
        filter_query: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> int:
        """
        统计文档数量
        """
        return await self.collection.count_documents(filter_query, session=session)

    @repo_handler("判断是否存在")
    async def exists(
        self,
        filter_query: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> bool:
        """判断是否存在符合条件的文档"""
        count = await self.collection.count_documents(filter_query, session=session)
        return count > 0


    @repo_handler("执行聚合查询")
    async def aggregate(
        self,
        pipeline: List[Dict[str, Any]],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> List[Dict[str, Any]]:
        """执行聚合查询"""
        cursor = self.collection.aggregate(pipeline, session=session)
        docs = await cursor.to_list(length=None)
        try:
            return self.convert_dict_to_pydanticModel(docs)
        except Exception as e:
            return docs

    @asynccontextmanager
    async def transaction(self):
        """
        事务上下文管理器
        Usage:
            async with repo.transaction() as session:
                await repo.insert_one(obj, session=session)
                await repo.update_one(filter_dict, update_data, session=session)
        """
        mongo_manager = get_mongo_manager()
        async with mongo_manager.transaction() as session:
            yield session

    @repo_handler("执行 bulk-upsert")
    async def bulk_upsert(
        self,
        objs: List[Dict[str, Any]],
        filter_keys: List[str],
        session: Optional[AsyncIOMotorClientSession] = None,
        *,
        upsert: bool = False,
        fetch_after_insert: bool = False,
    ) -> List[ModelInDB]:
        """
        批量 upsert 文档
        :param objs: 待 upsert 的数据列表
        :param filter_keys: 用于生成 upsert 匹配条件的字段名列表
        :param session: 可选事务会话
        :param upsert: 是否允许插入新文档，默认 False；如果开启，请区分 objs 的类型
        :param fetch_after_insert: 是否在 upsert 后重新查询文档，默认 False
        :return: 转换后的模型列表
        """
        if not objs:
            return []
        if not filter_keys:
            raise RepoValidationError("必须提供 filter_keys 以生成 upsert 匹配条件")

        # 构造 bulk 操作列表
        bulk_ops = []
        for doc in docs:
            filter_dict = {k: doc[k] for k in filter_keys if k in doc}
            if not filter_dict:
                raise RepoValidationError(
                    f"文档缺少 filter_keys 中的字段: {filter_keys}"
                )
            # 移除匹配条件字段，避免重复
            update_doc = {k: v for k, v in doc.items() if k not in filter_keys}
            bulk_ops.append(UpdateOne(filter_dict, {"$set": update_doc}, upsert=upsert))
        
        result = await self.collection.bulk_write(bulk_ops, ordered=False, session=session)

        if fetch_after_insert and result.upserted_ids:
            # 重新查询 upserted 文档
            upserted_ids = list(result.upserted_ids.values())
            inserted_docs = await self.collection.find(
                {"_id": {"$in": upserted_ids}}, session=session
            ).to_list(length=None)
            # 合并更新与插入结果
            id_to_doc = {d["_id"]: d for d in inserted_docs}
            final_docs = []
            for op, doc in zip(bulk_ops, docs):
                _id = result.upserted_ids.get(op)
                if _id:
                    final_docs.append(id_to_doc[_id])
                else:
                    # 更新场景，重新查询
                    reloaded = await self.collection.find_one(
                        op._filter, session=session
                    )
                    if reloaded:
                        final_docs.append(reloaded)
            return self.convert_dict_to_pydanticModel(final_docs)

        else:
            # 不重新查询，直接返回输入数据注入 id
            id_iter = (
                iter(result.upserted_ids.values())
                if result.upserted_ids
                else iter([])
            )
            for doc in docs:
                _id = next(id_iter, None)
                if _id:
                    doc["_id"] = _id
            return self.convert_dict_to_pydanticModel(docs)


    # -------------------------------------- 工具函数 --------------------------------------

    def _get_range_filter(
        self, field: str, min_value: Any = None, max_value: Any = None
    ) -> Dict[str, Any]:
        """生成 MongoDB 范围过滤条件"""
        range_filter = {}
        if min_value is not None:
            range_filter["$gte"] = min_value
        if max_value is not None:
            range_filter["$lte"] = max_value
        if not range_filter:
            self.logger.warning(f"生成空范围过滤条件，字段: {field}")
            return {}
        return {field: range_filter}


# import re
# from abc import ABC
# from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Union, Set
# from datetime import datetime, timezone

# from bson import ObjectId
# from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorClientSession
# from pymongo import UpdateOne
# from pymongo.errors import DuplicateKeyError, PyMongoError

# from src.db.mongo_db import get_mongo_manager

# from config.logging import get_repo_logger, get_trace_id
# from src.core.handler import repo_handler

# ModelType = TypeVar("ModelType", bound=BaseModel)
# CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
# UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


# class BaseRepo(Generic[ModelType, CreateSchemaType, UpdateSchemaType], ABC):
#     """MongoDB 基础仓储类 - 批量优先设计"""

#     MAX_FIND_LIMIT = 3000
#     ALLOWED_OPERATORS: Set[str] = {
#         "$or",
#         "$and",
#         "$nor",
#         "$not",
#         "$in",
#         "$nin",
#         "$exists",
#         "$gt",
#         "$gte",
#         "$lt",
#         "$lte",
#         "$eq",
#         "$ne",
#         "$all",
#         "$size",
#         "$regex",
#         "$options",
#         "$elemMatch",
#     }

#     def __init__(
#         self,
#         collection_name: str,
#         InDB_class: Type[ModelType],
#         Create_class: Type[CreateSchemaType],
#         Update_class: Type[UpdateSchemaType],
#         soft_delete: bool = True,
#     ):
#         """
#         初始化基础仓储
#             collection_name: MongoDB 集合名称
#             InDB_class: Pydantic 模型类
#             Create_class: Pydantic 创建模型类
#             Update_class: Pydantic 更新模型类
#         """
#         self.collection_name = collection_name
#         self._collection: Optional[AsyncIOMotorCollection] = None
#         self.InDB_class = InDB_class
#         self.Create_class = Create_class
#         self.Update_class = Update_class
#         self.soft_delete = soft_delete
#         self.logger = get_repo_logger(self.collection_name)
#         self._allow_fields: Set[str] = set(self.InDB_class.model_fields.keys())

#     @property
#     def collection(self) -> AsyncIOMotorCollection:
#         """获取 MongoDB 集合"""
#         if self._collection is None:
#             mongo_manager = get_mongo_manager()
#             self._collection = mongo_manager.get_collection(self.collection_name)
#         return self._collection

#     # -------------------------------------- 工具函数 --------------------------------------

#     def _get_range_filter(
#         self, field: str, min_value: Any = None, max_value: Any = None
#     ) -> Dict[str, Any]:
#         """生成 MongoDB 范围过滤条件"""
#         range_filter = {}
#         if min_value is not None:
#             range_filter["$gte"] = min_value
#         if max_value is not None:
#             range_filter["$lte"] = max_value
#         if not range_filter:
#             self.logger.warning(f"生成空范围过滤条件，字段: {field}")
#             return {}
#         return {field: range_filter}

#     def _convert_objectid_to_str(
#         self,
#         doc: Union[Dict[str, Any], List[Any], Any],
#     ) -> Union[Dict[str, Any], List[Any], Any]:
#         """高性能版：原地将 ObjectId 转为 str，并将 _id → id"""
#         if doc is None:
#             return None
#         stack = [doc]
#         isinstance_dict = isinstance
#         isinstance_list = isinstance
#         while stack:
#             current = stack.pop()
#             if isinstance_dict(current, dict):
#                 if "_id" in current:
#                     value = current.pop("_id")
#                     current["id"] = str(value) if isinstance(value, ObjectId) else value
#                 for k, v in list(current.items()):
#                     if isinstance_dict(v, dict) or isinstance_list(v, list):
#                         stack.append(v)
#                     elif isinstance(v, ObjectId):
#                         current[k] = str(v)
#             elif isinstance_list(current, list):
#                 for i, v in enumerate(current):
#                     if isinstance_dict(v, dict) or isinstance_list(v, list):
#                         stack.append(v)
#                     elif isinstance(v, ObjectId):
#                         current[i] = str(v)
#             elif isinstance(current, ObjectId):
#                 current = str(current)
#         return doc

#     def _convert_str_to_objectid(
#         self,
#         doc: Union[Dict[str, Any], List[Any], Any],
#     ) -> Union[Dict[str, Any], List[Any], Any]:
#         """高性能版：原地将 str 转为 ObjectId，并将 id → _id"""
#         if doc is None:
#             return None
#         stack = [doc]
#         isinstance_dict = isinstance
#         isinstance_list = isinstance
#         ObjectId_is_valid = ObjectId.is_valid
#         ObjectId_cls = ObjectId
#         while stack:
#             current = stack.pop()
#             if isinstance_dict(current, dict):
#                 # 修复：支持 id 为操作符字典或列表的场景
#                 if "id" in current:
#                     v = current.pop("id")
#                     if isinstance(v, str) and ObjectId_is_valid(v):
#                         current["_id"] = ObjectId_cls(v)
#                     elif isinstance(v, dict):
#                         # 转换常见操作符下的值
#                         for op_key, op_val in list(v.items()):
#                             if isinstance(op_val, str) and ObjectId_is_valid(op_val):
#                                 v[op_key] = ObjectId_cls(op_val)
#                             elif isinstance(op_val, list):
#                                 v[op_key] = [
#                                     ObjectId_cls(x)
#                                     if isinstance(x, str) and ObjectId_is_valid(x)
#                                     else x
#                                     for x in op_val
#                                 ]
#                         current["_id"] = v
#                     elif isinstance(v, list):
#                         current["_id"] = [
#                             ObjectId_cls(x)
#                             if isinstance(x, str) and ObjectId_is_valid(x)
#                             else x
#                             for x in v
#                         ]
#                     else:
#                         # 其他类型（很少见），仍然改名以保证查询字段正确
#                         current["_id"] = v

#                 for k, v in list(current.items()):
#                     if isinstance_dict(v, dict) or isinstance_list(v, list):
#                         stack.append(v)
#                     elif isinstance(v, str) and ObjectId_is_valid(v):
#                         if k.endswith("_id"):
#                             current[k] = ObjectId_cls(v)
#                     elif isinstance_list(v, list):
#                         if k.endswith("_ids"):
#                             current[k] = [
#                                 ObjectId_cls(x)
#                                 if isinstance(x, str) and ObjectId_is_valid(x)
#                                 else x
#                                 for x in v
#                             ]
#             elif isinstance_list(current, list):
#                 for i, v in enumerate(current):
#                     if isinstance_dict(v, dict) or isinstance_list(v, list):
#                         stack.append(v)
#                     elif isinstance(v, str) and ObjectId_is_valid(v):
#                         current[i] = ObjectId_cls(v)
#         return doc

#     def _prepare_create_documents(
#         self, data_list: List[Union[BaseModel, Dict[str, Any]]]
#     ) -> List[Dict[str, Any]]:
#         """批量准备文档用于数据库存储"""
#         dicts = []
#         now = datetime.now(timezone.utc)
#         is_model_instance = isinstance(data_list[0], BaseModel)
#         if is_model_instance:
#             dicts = [d.model_dump() for d in data_list]
#         else:
#             dicts = [d.copy() for d in data_list]
#         for doc in dicts:
#             doc.setdefault("created_at", now)
#             doc.setdefault("updated_at", now)
#         return self._convert_str_to_objectid(dicts)

#     def _prepare_create_document(
#         self, data: Union[BaseModel, Dict[str, Any]]
#     ) -> Dict[str, Any]:
#         """准备单个文档用于数据库存储（调用批量方法）"""
#         return self._prepare_create_documents([data])[0]

#     def _prepare_update_documents(
#         self, data_list: List[Union[BaseModel, Dict[str, Any]]]
#     ) -> List[Dict[str, Any]]:
#         """批量准备更新数据（仅保留更新字段 | 适用于 bulk update，即更新数据不同的情况）"""
#         dicts = []
#         is_model_instance = isinstance(data_list[0], BaseModel)
#         if is_model_instance:
#             dicts = [d.model_dump(exclude_unset=True) for d in data_list]
#         else:
#             dicts = [d.copy() for d in data_list]
#         now = datetime.now(timezone.utc)
#         for doc in dicts:
#             doc.setdefault("updated_at", now)
#         return self._convert_str_to_objectid(dicts)

#     def _prepare_update_document(
#         self, data: Union[BaseModel, Dict[str, Any]], *, upsert: bool = False
#     ) -> Dict[str, Any]:
#         """准备更新数据（仅保留更新字段）"""
#         return self._prepare_update_documents([data])[0]

#     def _convert_db_documents(self, docs: List[Dict[str, Any]]) -> List[ModelType]:
#         """批量从数据库文档转换为 Pydantic 模型"""
#         filterd_docs = [d for d in docs if d is not None]
#         if not filterd_docs:
#             return []
#         converted_docs = self._convert_objectid_to_str(filterd_docs)
#         results, errors = ([], [])
#         for i, doc in enumerate(converted_docs):
#             try:
#                 results.append(self.InDB_class(**doc))
#             except PydanticValidationError as e:
#                 # 收集索引与原始异常，保留用于合成摘要与异常链
#                 errors.append((i, e))
#         if errors:
#             msg = "; ".join(f"[第{idx}条文档] {err}" for idx, err in errors)
#             # 保留异常链，指向首个底层异常（其堆栈由 Repo 层统一打印）
#             raise RepoValidationError(f"文档转换失败: {msg}") from errors[0][1]
#         return results

#     def _convert_db_document(
#         self, doc: Optional[Dict[str, Any]]
#     ) -> Optional[ModelType]:
#         """从数据库文档转换为 Pydantic 模型（调用批量方法）"""
#         results = self._convert_db_documents([doc])
#         return results[0] if results else None

#     def _validate_filter_dict(self, filter_dict: Dict[str, Any]) -> None:
#         """
#         验证过滤条件中的未知字段与非法操作符。
#         支持：
#         - 字段名（来自 InDB_class.model_fields）
#         - 常见 Mongo 操作符：$or, $and, $in, $gt, $lt, ...（见 allowed_operators）
#         - 点号字段（如 parameters.library_id），当根段是模型字段时允许
#         """
#         allow_fields: Set[str] = self._allow_fields
#         allowed_operators: Set[str] = self.ALLOWED_OPERATORS

#         def _err(msg: str):
#             raise RepoValidationError(msg)

#         def _is_allowed_field(key: str) -> bool:
#             if key in allow_fields:
#                 return True
#             if "." in key:
#                 root = key.split(".", 1)[0]
#                 return root in allow_fields
#             return False

#         def validate(node: Any, path: str = "") -> None:
#             if isinstance(node, dict):
#                 for k, v in node.items():
#                     current_path = f"{path}.{k}" if path else k
#                     if _is_allowed_field(k):
#                         if isinstance(v, dict):
#                             for op, op_val in v.items():
#                                 op_path = f"{current_path}.{op}"
#                                 if isinstance(op, str) and op.startswith("$"):
#                                     if op not in allowed_operators:
#                                         _err(f"未知操作符 {op} 在 {op_path}")
#                                     if isinstance(op_val, (dict, list)):
#                                         validate(op_val, op_path)
#                                 else:
#                                     validate(v, current_path)
#                                     break
#                         elif isinstance(v, list):
#                             for idx, item in enumerate(v):
#                                 validate(item, f"{current_path}[{idx}]")
#                         else:
#                             pass
#                     elif isinstance(k, str) and k.startswith("$"):
#                         if k not in allowed_operators:
#                             _err(f"未知操作符 {k} 在 {current_path}")
#                         if k in {"$or", "$and", "$nor"}:
#                             if not isinstance(v, list):
#                                 _err(f"{k} 必须是列表，位于 {current_path}")
#                             for idx, item in enumerate(v):
#                                 if not isinstance(item, dict):
#                                     _err(
#                                         f"{k} 的元素必须是 dict，位于 {current_path}[{idx}]"
#                                     )
#                                 validate(item, f"{current_path}[{idx}]")
#                         elif k == "$not":
#                             if not isinstance(v, dict):
#                                 _err(f"{k} 必须是 dict，位于 {current_path}")
#                             validate(v, current_path)
#                         elif isinstance(v, (dict, list)):
#                             validate(v, current_path)
#                     else:
#                         _err(f"过滤条件中包含未知字段: '{k}'，位于 {current_path}")
#             elif isinstance(node, list):
#                 for idx, item in enumerate(node):
#                     validate(item, f"{path}[{idx}]")
#             else:
#                 pass

#         validate(filter_dict)

#     def _normalize_projection(
#         self, projection: Optional[Union[Dict[str, Any], List[str]]]
#     ) -> Optional[Dict[str, int]]:
#         """
#         规范化并校验投影：
#         - 支持 list[str]（统一为包含投影）
#         - 支持 dict（值为 0/1 或 bool）
#         - 不允许同时包含包含和排除（除非仅排除 _id）
#         - 校验字段存在于模型，允许点号字段根段在模型字段里
#         """
#         if projection is None:
#             return None
#         allow_fields: Set[str] = self._allow_fields

#         def _is_allowed_field(key: str) -> bool:
#             if key in allow_fields:
#                 return True
#             if "." in key:
#                 root = key.split(".", 1)[0]
#                 return root in allow_fields
#             return False

#         if isinstance(projection, (list, tuple, set)):
#             fields = list(projection)
#             for f in fields:
#                 if not isinstance(f, str):
#                     raise RepoValidationError("投影字段必须是字符串")
#                 if f != "id" and (not _is_allowed_field(f)):
#                     raise RepoValidationError(f"未知投影字段: {f}")
#             return {f: 1 for f in fields}
#         if isinstance(projection, dict):
#             normalized: Dict[str, int] = {}
#             includes: Set[str] = set()
#             excludes: Set[str] = set()
#             for k, v in projection.items():
#                 if not isinstance(k, str):
#                     raise RepoValidationError("投影字段名必须是字符串")
#                 if k != "id" and (not _is_allowed_field(k)):
#                     raise RepoValidationError(f"未知投影字段: {k}")
#                 if v in (1, True):
#                     normalized[k] = 1
#                     includes.add(k)
#                 elif v in (0, False):
#                     normalized[k] = 0
#                     excludes.add(k)
#                 else:
#                     raise RepoValidationError("投影值必须是 0/1 或布尔")
#             if includes and excludes and (excludes != {"id"}):
#                 raise RepoValidationError("投影不能同时包含包含与排除（除非仅排除 id）")
#             return normalized
#         raise RepoValidationError("投影参数必须是 dict 或 list[str]")

#     # -------------------------------------- 增删查改+恢复 --------------------------------------
#     @repo_handler("批量插入文档")
#     async def insert_many(
#         self,
#         objs: List[CreateSchemaType],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         fetch_after_insert: bool = False,
#         use_validate: bool = False,
#     ) -> List[ModelType]:
#         """
#         批量插入文档 - 核心实现
#         默认遇到重复直接抛异常，所以如果大批量插入，请在上层结合业务逻辑进行过滤重复项
#         :param fetch_after_insert: 是否在插入后重新查询文档，默认 False 直接返回 id注入的输入 objs
#         :param use_validate: 是否在插入前验证数据，默认 False, 开发阶段测试用
#         """
#         if not objs:
#             return []
#         try:
#             if use_validate:
#                 validated_objs = [
#                     self.Create_class.model_validate(obj.model_dump(), strict=True)
#                     for obj in objs
#                 ]
#             else:
#                 validated_objs = objs
#             docs = self._prepare_create_documents(validated_objs)
#             # 默认开启软删除，插入时设置 is_deleted=False
#             if self.soft_delete:
#                 for doc in docs:
#                     doc.setdefault("is_deleted", False)
#             result = await self.collection.insert_many(docs, session=session)
#             if fetch_after_insert:
#                 inserted_docs = await self.collection.find(
#                     {"_id": {"$in": result.inserted_ids}}, session=session
#                 ).to_list(length=None)
#                 id_index = {id_: i for i, id_ in enumerate(result.inserted_ids)}
#                 inserted_docs.sort(key=lambda d: id_index.get(d["_id"], 0))
#             else:
#                 id_iter = iter(result.inserted_ids)
#                 for doc in docs:
#                     doc["_id"] = next(id_iter)
#             return self._convert_db_documents(docs)
#         except PydanticValidationError as e:
#             raise RepoValidationError(f"数据验证失败: {e}") from e
#         except DuplicateKeyError as e:
#             raise RepoValidationError(f"文档已存在，无法重复插入: {e}") from e
#         except PyMongoError as e:
#             raise BaseRepoException(f"批量插入失败: {e}") from e

#     @repo_handler("查找多个文档")
#     async def find_many(
#         self,
#         filter_dict: Optional[Dict[str, Any]] = None,
#         skip: int = 0,
#         limit: int = 1000,
#         sort: Optional[List[tuple]] = None,
#         projection: Optional[Union[Dict[str, int], List[str]]] = None,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = False,
#     ) -> List[Union[ModelType, Dict[str, Any]]]:
#         """查找多个文档 - 核心实现
#         注意：如果 limit 大于 1000，请考虑使用 iter-many
#         注意：深分页场景应使用基于 _id 的分页，需要调用方手动拼接 filter_dict 中的 _id 条件 并在 sort 中添加 (_id, 1) 或 (_id, -1)
#         注意：基于 _id 的分页请确保，当前集合中 存在 sort && -id 的复式索引，否则性能可能会受到影响
#         或者，也可以采用其他符合 唯一性的 复式索引 的 字段 替代 _id 字段
#         """
#         if limit > self.MAX_FIND_LIMIT:
#             raise RepoValidationError(
#                 f"单次查找最大返回文档数为 {self.MAX_FIND_LIMIT}，当前请求为 {limit}, 请分页查找"
#             )
#         try:
#             filter_dict = dict(filter_dict or {})
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             normalized_projection = self._normalize_projection(projection)
#             cursor = self.collection.find(
#                 filter_dict, projection=normalized_projection, session=session
#             )
#             if skip > 0 and (not last_result):
#                 cursor = cursor.skip(skip)
#             if limit > 0:
#                 cursor = cursor.limit(limit)
#             if sort and isinstance(sort, list):
#                 cursor = cursor.sort(sort)
#             docs = await cursor.to_list(length=limit)
#             if normalized_projection is not None:
#                 return self._convert_objectid_to_str(docs)
#             return self._convert_db_documents(docs)
#         except PydanticValidationError as e:
#             raise RepoValidationError(f"数据验证失败: {e}")
#         except PyMongoError as e:
#             raise BaseRepoException(f"查找文档失败: {e}")

#     @repo_handler("查找很多很多个文档")
#     async def iter_many(
#         self,
#         filter_dict: Optional[Dict[str, Any]] = None,
#         skip: int = 0,
#         limit: int = 1000,
#         sort: Optional[List[tuple]] = None,
#         projection: Optional[Union[Dict[str, int], List[str]]] = None,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = False,
#     ) -> List[Union[ModelType, Dict[str, Any]]]:
#         """查找多个文档 - 核心实现
#         注意：深分页场景应使用基于 _id 的分页，需要调用方手动拼接 filter_dict 中的 _id 条件 并在 sort 中添加 (_id, 1) 或 (_id, -1)
#         注意：基于 _id 的分页请确保，当前集合中 存在 sort && -id 的复式索引，否则性能可能会受到影响
#         或者，也可以采用其他符合 唯一性的 复式索引 的 字段 替代 _id 字段
#         """
#         try:
#             filter_dict = dict(filter_dict or {})
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             # 具体的软删除查询逻辑请在各个子类中实现
#             # if self.soft_delete:
#             #     filter_dict['is_deleted'] = False
#             normalized_projection = self._normalize_projection(projection)
#             cursor = self.collection.find(
#                 filter_dict, projection=normalized_projection, session=session
#             )
#             if skip > 0 and (not last_result):
#                 cursor = cursor.skip(skip)
#             if limit > 0:
#                 cursor = cursor.limit(limit)
#             if sort and isinstance(sort, list):
#                 cursor = cursor.sort(sort)
#             async for doc in cursor:
#                 if normalized_projection is not None:
#                     doc = self._convert_objectid_to_str(doc)
#                 else:
#                     doc = self._convert_db_documents(doc)
#         except PydanticValidationError as e:
#             raise RepoValidationError(f"数据验证失败: {e}")
#         except PyMongoError as e:
#             raise BaseRepoException(f"查找文档失败: {e}")

#     @repo_handler("批量更新文档")
#     async def update_many(
#         self,
#         filter_dict: Dict[str, Any],
#         update_data: UpdateSchemaType,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         fetch_after_update: bool = False,
#         use_validate: bool = False,
#     ) -> Union[int, List[ModelType]]:
#         """
#         批量更新文档 - 核心实现
#         :param fetch_after_update: 是否在更新后重新查询文档，默认 False
#         :param require_cache: 是否要求返回受影响的id列表用来更新cache，默认 False
#         """
#         try:
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#                 if isinstance(update_data, BaseModel):
#                     _ = self.Update_class.model_validate(
#                         update_data.model_dump(), strict=True
#                     )
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             # 如果当前类开启了软删除模式，那么不允许直接修改已被软删除的文档
#             if self.soft_delete:
#                 filter_dict["is_deleted"] = False
#             update_doc = self._prepare_update_document(update_data)
#             if fetch_after_update:
#                 docs_to_update = await self.collection.find(
#                     filter_dict, session=session
#                 ).to_list(length=None)
#             result = await self.collection.update_many(
#                 filter_dict, {"$set": update_doc}, session=session
#             )
#             if fetch_after_update and result.modified_count > 0:
#                 updated_docs = await self.collection.find(
#                     {"_id": {"$in": [doc["_id"] for doc in docs_to_update]}},
#                     session=session,
#                 ).to_list(length=None)
#                 return self._convert_db_documents(updated_docs)
#             return result.modified_count
#         except PydanticValidationError as e:
#             raise RepoValidationError(f"数据验证失败: {e}")
#         except PyMongoError as e:
#             raise BaseRepoException(f"批量更新失败: {e}")

#     @repo_handler("批量删除文档")
#     async def delete_many(
#         self,
#         filter_dict: Dict[str, Any],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         soft_delete: bool = True,
#         use_validate: bool = True,
#     ) -> int:
#         """
#         批量删除文档 - 核心实现，默认开启字段验证
#         """
#         try:
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = self._convert_str_to_objectid(filter_dict)

#             if soft_delete and self.soft_delete:
#                 now = datetime.now(timezone.utc)
#                 filter_dict["is_deleted"] = False
#                 update_doc = {"is_deleted": True, "deleted_at": now, "updated_at": now}
#                 result = await self.collection.update_many(
#                     filter_dict, {"$set": update_doc}, session=session
#                 )
#                 return result.modified_count

#             elif soft_delete and not self.soft_delete:
#                 raise BaseRepoException(
#                     "当前类未开启软删除模式，无法执行批量软删除操作"
#                 )

#             else:
#                 result = await self.collection.delete_many(filter_dict, session=session)
#                 return result.deleted_count

#         except PyMongoError as e:
#             raise BaseRepoException(f"批量删除失败: {e}")

#     @repo_handler("批量恢复文档")
#     async def restore_many(
#         self,
#         filter_dict: Dict[str, Any],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = True,
#         fetch_after_restore: bool = True,
#     ) -> Union[int, List[ModelType]]:
#         """
#         批量恢复文档 - 核心实现
#         """
#         try:
#             if self.soft_delete is False:
#                 raise BaseRepoException("当前类未开启软删除模式，无法恢复文档")

#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             filter_dict["is_deleted"] = True
#             if fetch_after_restore:
#                 docs_to_restore = await self.collection.find(
#                     filter_dict, session=session
#                 ).to_list(length=None)
#             update_doc = {
#                 "is_deleted": False,
#                 "deleted_at": None,
#                 "updated_at": datetime.now(timezone.utc),
#             }
#             result = await self.collection.update_many(
#                 filter_dict, {"$set": update_doc}, session=session
#             )
#             if fetch_after_restore:
#                 if result.modified_count == 0:
#                     return []
#                 restored_docs = await self.collection.find(
#                     {"_id": {"$in": [doc["_id"] for doc in docs_to_restore]}},
#                     session=session,
#                 ).to_list(length=None)
#                 return self._convert_db_documents(restored_docs)
#             return result.modified_count
#         except PyMongoError as e:
#             raise BaseRepoException(f"批量恢复失败: {e}")

#     @repo_handler("插入单个文档")
#     async def insert_one(
#         self,
#         obj: CreateSchemaType,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         fetch_after_insert: bool = False,
#         use_validate: bool = False,
#     ) -> ModelType:
#         """插入单个文档 - 调用批量方法"""
#         results = await self.insert_many(
#             [obj],
#             session=session,
#             fetch_after_insert=fetch_after_insert,
#             use_validate=use_validate,
#         )
#         return results[0]

#     # @repo_handler("查找单个文档")
#     async def find_one(
#         self,
#         filter_dict: Dict[str, Any],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = False,
#     ) -> Optional[ModelType]:
#         """
#         查找单个文档 - 调用批量方法
#         """
#         results = await self.find_many(
#             filter_dict,
#             0,
#             1,
#             None,
#             None,
#             session=session,
#             use_validate=use_validate,
#         )
#         return results[0] if results else None

#     @repo_handler("更新单个文档")
#     async def update_one(
#         self,
#         filter_dict: Dict[str, Any],
#         update_data: Union[UpdateSchemaType],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = False,
#     ) -> Optional[ModelType]:
#         """
#         更新单个文档 - 使用 find-one-and-update 方法 优化处理速率
#         """
#         try:
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#                 if isinstance(update_data, BaseModel):
#                     _ = self.Update_class.model_validate(
#                         update_data.model_dump(), strict=True
#                     )
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             # 如果当前类开启了软删除模式，那么不允许直接修改已被软删除的文档
#             if self.soft_delete:
#                 filter_dict["is_deleted"] = False
#             update_doc = self._prepare_update_document(update_data)
#             result = await self.collection.find_one_and_update(
#                 filter_dict, {"$set": update_doc}, session=session, return_document=True
#             )
#             return self._convert_db_document(result) if result else None
#         except PydanticValidationError as e:
#             raise RepoValidationError(f"数据验证失败: {e}")
#         except PyMongoError as e:
#             raise BaseRepoException(f"更新文档失败: {e}")

#     # @repo_handler("删除单个文档")
#     async def delete_one(
#         self,
#         filter_dict: Dict[str, Any],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         soft_delete: bool = True,
#         use_validate: bool = True,
#     ) -> bool:
#         """
#         删除单个文档 - 调用批量方法
#         """
#         count = await self.delete_many(
#             filter_dict=filter_dict,
#             session=session,
#             soft_delete=soft_delete,
#             use_validate=use_validate,
#         )
#         return count > 0

#     @repo_handler("恢复单个文档")
#     async def restore_one(
#         self,
#         filter_dict: Dict[str, Any],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = False,
#     ) -> Optional[ModelType]:
#         """
#         恢复单个文档 - 调用批量方法
#         """
#         try:
#             if self.soft_delete is False:
#                 raise BaseRepoException("当前类未开启软删除模式，无法恢复文档")

#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             filter_dict["is_deleted"] = True
#             update_doc = {
#                 "is_deleted": False,
#                 "deleted_at": None,
#                 "updated_at": datetime.now(timezone.utc),
#             }
#             result = await self.collection.find_one_and_update(
#                 filter_dict, {"$set": update_doc}, session=session, return_document=True
#             )
#             return self._convert_db_document(result) if result else None
#         except PyMongoError as e:
#             raise BaseRepoException(f"批量恢复失败: {e}")

#     # -------------------------------------- 热门函数 --------------------------------------
#     async def find_by_id(
#         self, doc_id: str, session: Optional[AsyncIOMotorClientSession] = None
#     ) -> Optional[ModelType]:
#         """根据ID查找文档，不进行类型检查"""
#         return await self.find_one({"id": doc_id}, session=session)

#     async def update_by_id(
#         self,
#         doc_id: str,
#         update_data: UpdateSchemaType,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         use_validate: bool = False,
#     ) -> Optional[ModelType]:
#         """根据ID更新文档，支持类型检查，确保 update_data 正确"""
#         return await self.update_one(
#             {"id": doc_id}, update_data, session=session, use_validate=use_validate
#         )

#     async def delete_by_id(
#         self,
#         doc_id: str,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         soft_delete: bool = True,
#     ) -> bool:
#         """根据ID删除文档，不进行类型检查"""
#         return await self.delete_one(
#             {"id": doc_id}, session=session, soft_delete=soft_delete, use_validate=False
#         )

#     async def restore_by_id(
#         self, doc_id: str, session: Optional[AsyncIOMotorClientSession] = None
#     ) -> Optional[ModelType]:
#         """根据ID恢复文档，不进行类型检查"""
#         return await self.restore_one(
#             {"id": doc_id}, session=session, use_validate=False
#         )

#     async def find_by_ids(
#         self, doc_ids: List[str], session: Optional[AsyncIOMotorClientSession] = None
#     ) -> Optional[ModelType]:
#         """根据ID列表查找文档，不进行类型检查"""
#         return await self.find_many({"id": {"$in": doc_ids}}, session=session)

#     async def update_by_ids(
#         self,
#         doc_ids: List[str],
#         update_data: UpdateSchemaType,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         use_validate: bool = False,
#     ) -> Optional[List[ModelType]]:
#         """根据ID列表批量更新文档，支持类型检查，确保 update_data 正确"""
#         return await self.update_many(
#             {"id": {"$in": doc_ids}},
#             update_data,
#             session=session,
#             use_validate=use_validate,
#             fetch_after_update=True,
#         )

#     async def delete_by_ids(
#         self,
#         doc_ids: List[str],
#         session: Optional[AsyncIOMotorClientSession] = None,
#         soft_delete: bool = True,
#     ) -> bool:
#         """根据ID列表批量删除文档，不进行类型检查"""
#         return await self.delete_many(
#             {"id": {"$in": doc_ids}},
#             session=session,
#             soft_delete=soft_delete,
#             use_validate=False,
#         )

#     async def restore_by_ids(
#         self, doc_ids: List[str], session: Optional[AsyncIOMotorClientSession] = None
#     ) -> Optional[ModelType]:
#         """根据ID列表批量恢复文档，不进行类型检查"""
#         return await self.restore_many(
#             {"id": {"$in": doc_ids}}, session=session, use_validate=False
#         )

#     # -------------------------------------- 通用数据操作增强 --------------------------------------
#     @repo_handler("统计文档数量")
#     async def count(
#         self,
#         filter_dict: Optional[Dict[str, Any]] = None,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = False,
#     ) -> int:
#         """
#         统计文档数量
#         """
#         try:
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = dict(filter_dict or {})
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             return await self.collection.count_documents(filter_dict, session=session)
#         except PyMongoError as e:
#             raise BaseRepoException(f"统计文档失败: {e}")

#     @repo_handler("判断是否存在")
#     async def exists(
#         self,
#         filter_dict: Optional[Dict[str, Any]] = None,
#         session: Optional[AsyncIOMotorClientSession] = None,
#         *,
#         use_validate: bool = True,
#     ) -> bool:
#         """判断是否存在符合条件的文档，推荐开启校验功能，避免影响后续操作"""
#         try:
#             filter_dict = dict(filter_dict or {})
#             if use_validate:
#                 self._validate_filter_dict(filter_dict)
#             filter_dict = self._convert_str_to_objectid(filter_dict)
#             count = await self.collection.count_documents(
#                 filter_dict, limit=1, session=session
#             )
#             return count > 0
#         except PyMongoError as e:
#             raise BaseRepoException(f"判断文档是否存在失败: {e}")

#     @repo_handler("执行聚合查询")
#     async def aggregate(
#         self,
#         pipeline: List[Dict[str, Any]],
#         session: Optional[AsyncIOMotorClientSession] = None,
#     ) -> List[Dict[str, Any]]:
#         """执行聚合查询"""
#         try:
#             pipeline = self._convert_str_to_objectid(pipeline)
#             cursor = self.collection.aggregate(pipeline, session=session)
#             docs = await cursor.to_list(length=None)
#             return [self._convert_objectid_to_str(doc) for doc in docs]
#         except PyMongoError as e:
#             raise BaseRepoException(f"聚合查询失败: {e}")

#     @asynccontextmanager
#     async def transaction(self):
#         """
#         事务上下文管理器
#         Usage:
#             async with repo.transaction() as session:
#                 await repo.insert_one(obj, session=session)
#                 await repo.update_one(filter_dict, update_data, session=session)
#         """
#         mongo_manager = get_mongo_manager()
#         async with mongo_manager.transaction() as session:
#             yield session

#     @repo_handler("执行 bulk-upsert")
#     async def bulk_upsert(
#         self,
#         objs: List[CreateSchemaType],
#         filter_keys: List[str],
#         *,
#         upsert: bool = True,
#         fetch_after_insert: bool = False,
#         session: Optional[AsyncIOMotorClientSession] = None,
#     ) -> List[ModelType]:
#         """
#         批量 upsert 文档
#         :param objs: 待 upsert 的数据列表
#         :param filter_keys: 用于生成 upsert 匹配条件的字段名列表
#         :param upsert: 是否允许插入新文档，默认 True
#         :param fetch_after_insert: 是否在 upsert 后重新查询文档，默认 False
#         :param session: 可选事务会话
#         :return: 转换后的模型列表
#         """
#         if not objs:
#             return []
#         if not filter_keys:
#             raise RepoValidationError("必须提供 filter_keys 以生成 upsert 匹配条件")

#         # 准备文档
#         docs = self._prepare_create_documents(objs)
#         if self.soft_delete:
#             for doc in docs:
#                 doc.setdefault("is_deleted", False)

#         # 构造 bulk 操作列表
#         bulk_ops = []
#         for doc in docs:
#             filter_dict = {k: doc[k] for k in filter_keys if k in doc}
#             if not filter_dict:
#                 raise RepoValidationError(
#                     f"文档缺少 filter_keys 中的字段: {filter_keys}"
#                 )
#             # 移除匹配条件字段，避免重复
#             update_doc = {k: v for k, v in doc.items() if k not in filter_keys}
#             # 设置 updated_at
#             update_doc.setdefault("updated_at", datetime.now(timezone.utc))
#             bulk_ops.append(UpdateOne(filter_dict, {"$set": update_doc}, upsert=upsert))

#         try:
#             result = await self.collection.bulk_write(
#                 bulk_ops, ordered=False, session=session
#             )
#             if fetch_after_insert and result.upserted_ids:
#                 # 重新查询 upserted 文档
#                 upserted_ids = list(result.upserted_ids.values())
#                 inserted_docs = await self.collection.find(
#                     {"_id": {"$in": upserted_ids}}, session=session
#                 ).to_list(length=None)
#                 # 合并更新与插入结果
#                 id_to_doc = {d["_id"]: d for d in inserted_docs}
#                 final_docs = []
#                 for op, doc in zip(bulk_ops, docs):
#                     _id = result.upserted_ids.get(op)
#                     if _id:
#                         final_docs.append(id_to_doc[_id])
#                     else:
#                         # 更新场景，重新查询
#                         reloaded = await self.collection.find_one(
#                             op._filter, session=session
#                         )
#                         if reloaded:
#                             final_docs.append(reloaded)
#                 return self._convert_db_documents(final_docs)
#             else:
#                 # 不重新查询，直接返回输入数据注入 id
#                 id_iter = (
#                     iter(result.upserted_ids.values())
#                     if result.upserted_ids
#                     else iter([])
#                 )
#                 for doc in docs:
#                     _id = next(id_iter, None)
#                     if _id:
#                         doc["_id"] = _id
#                 return self._convert_db_documents(docs)
#         except PyMongoError as e:
#             raise BaseRepoException(f"bulk upsert 失败: {e}") from e

import json
from typing import TypeVar, Generic, Optional, List, Dict, Any, Type, Callable
from motor.motor_asyncio import AsyncIOMotorClientSession
from pydantic import BaseModel, ValidationError as PydanticValidationError

from config.logging import get_logic_logger
from src.core.handler import logic_handler
from src.core.exceptions import NotFoundError
from src.repos.mongo_repos.base_repo import BaseRepo
from src.repos.cache_repos.base_redis_repo import DualLayerCache

# Pydantic 模型类型
InDBT = TypeVar("InDBT", bound=BaseModel)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)
ReadT = TypeVar("ReadT", bound=BaseModel)


class BaseLogic(Generic[InDBT, CreateT, UpdateT, ReadT]):
    """
    通用逻辑层
    - 默认使用 BaseRepo + DualLayerCache
    - 仅删除类方法返回删除数量，其余返回 Read 或 List[Read]
    """

    def __init__(
        self,
        repo: BaseRepo[InDBT, CreateT, UpdateT],
        read_model: Type[ReadT],
        cache_repo: Optional[DualLayerCache] = None,
        *,
        namespace: Optional[str] = None,
        id_field: str = "id",
        default_expire: Optional[int] = None,
    ) -> None:
        self.repo = repo
        self.read_model = read_model
        self.cache_repo = cache_repo or DualLayerCache(
            namespace=namespace or getattr(repo, "collection_name", "default"),
            default_expire=default_expire,
            id_field=id_field,
        )
        self.logger = get_logic_logger(self.__class__.__name__)

    def _build_search_key(self, **kwargs) -> str:
        # 将 None 转为空值，列表排序，浮点格式规范化
        def normalize(v):
            if v is None:
                return ""
            if isinstance(v, list):
                return sorted(v)
            if isinstance(v, float):
                return round(v, 2)
            return v

        normalized = {k: normalize(v) for k, v in kwargs.items() if k not in {"self", "session"}}
        json_str = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return f"{self.__class__.__name__}:{hash(json_str)}"

    # ---------- 读取 ----------

    async def get_by_id(
        self, obj_id: str, session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[ReadT]:
        # 1) 先尝试缓存
        cached = await self.cache_repo.get_detail(obj_id)
        if cached:
            try:
                return self.read_model(**cached)
            except PydanticValidationError:
                # 缓存不合法，回源并重建缓存
                pass

        # 2) 回源 DB
        in_db = await self.repo.find_by_id(obj_id, session=session)
        if not in_db:
            raise NotFoundError("对象不存在或已删除")

        # 3) 回填缓存并返回
        await self.cache_repo.cache_detail(in_db.model_dump())
        return self.read_model(**in_db.model_dump())

    async def get_by_ids(
        self,
        obj_ids: List[str],
        session: Optional[AsyncIOMotorClientSession] = None,
        require_sort: bool = True,
    ) -> List[ReadT]:
        if not obj_ids:
            return []

        # 1) 尝试批量缓存
        cached_details = await self.cache_repo.get_details_batch(obj_ids)
        id_to_read: Dict[str, ReadT] = {}
        missing_ids: List[str] = []

        for oid, din in zip(obj_ids, cached_details):
            if din is not None:
                try:
                    id_to_read[oid] = self.read_model(**din)
                except PydanticValidationError:
                    missing_ids.append(oid)
            else:
                missing_ids.append(oid)

        # 2) 对缺失部分回源并批量回填
        if missing_ids:
            db_items = await self.repo.find_by_ids(missing_ids, session=session)
            if db_items:
                payloads = [m.model_dump() for m in db_items]
                await self.cache_repo.cache_details_batch(payloads)
                for m in db_items:
                    id_to_read[m.id] = self.read_model(**m.model_dump())

        # 3) 按输入顺序返回（默认保持原顺序）
        result: List[ReadT] = [id_to_read[oid] for oid in obj_ids if oid in id_to_read]
        if require_sort:
            return result
        return list(id_to_read.values())

    # ---------- 创建 ----------

    async def create(
        self, data: CreateT, session: Optional[AsyncIOMotorClientSession] = None
    ) -> ReadT:
        in_db = await self.repo.insert_one(data, session=session)
        # 写入缓存
        await self.cache_repo.cache_detail(in_db.model_dump())
        await self.cache_repo.delete_search_cache_all()
        return self.read_model(**in_db.model_dump())

    async def create_batch(
        self, data: List[CreateT], session: Optional[AsyncIOMotorClientSession] = None
    ) -> List[ReadT]:
        if not data:
            return []
        inserted = await self.repo.insert_many(data, session=session)
        # 写入缓存
        await self.cache_repo.cache_details_batch([m.model_dump() for m in inserted])
        await self.cache_repo.delete_search_cache_all()
        return [self.read_model(**m.model_dump()) for m in inserted]

    # ---------- 更新 ----------

    async def update_by_ids(
        self,
        obj_ids: List[str],
        patch: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> List[ReadT]:
        if not obj_ids or not patch:
            return []
        updated = await self.repo.update_by_ids(obj_ids, patch, session=session)
        # 回填缓存
        for m in updated or []:
            await self.cache_repo.cache_detail(m.model_dump())
        await self.cache_repo.delete_search_cache_all()
        return [self.read_model(**m.model_dump()) for m in (updated or [])]

    async def update_by_id(
        self,
        obj_id: str,
        patch: Dict[str, Any],
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> Optional[ReadT]:
        if not obj_id or not patch:
            return None
        updated = await self.repo.update_by_id(obj_id, patch, session=session)
        if not updated:
            raise NotFoundError("对象不存在或已删除")
        # 回填缓存
        await self.cache_repo.cache_detail(updated.model_dump())
        await self.cache_repo.delete_search_cache_all()
        return self.read_model(**updated.model_dump())

    # ---------- 删除 ----------

    async def deleted_by_ids(
        self,
        obj_ids: List[str],
        soft_delete: bool = True,
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> int:
        if not obj_ids:
            return 0
        count = await self.repo.delete_by_ids(obj_ids, soft_delete=soft_delete, session=session)
        # 清理缓存
        await self.cache_repo.delete_details_batch(obj_ids)
        await self.cache_repo.delete_search_cache_all()
        return count

    async def delete_by_id(
        self,
        obj_id: str,
        soft_delete: bool = True,
        session: Optional[AsyncIOMotorClientSession] = None,
    ) -> int:
        if not obj_id:
            return 0
        count = await self.repo.delete_by_id(obj_id, soft_delete=soft_delete, session=session)
        # 清理缓存
        await self.cache_repo.clear_item_cache(obj_id)
        await self.cache_repo.delete_search_cache_all()
        return count

    # ---------- 恢复 ----------

    async def restore_by_ids(
        self, obj_ids: List[str], session: Optional[AsyncIOMotorClientSession] = None
    ) -> List[ReadT]:
        if not obj_ids:
            return []
        restored = await self.repo.restore_by_ids(obj_ids, session=session)
        for m in restored or []:
            await self.cache_repo.cache_detail(m.model_dump())
        await self.cache_repo.delete_search_cache_all()
        return [self.read_model(**m.model_dump()) for m in (restored or [])]

    async def restore_by_id(
        self, obj_id: str, session: Optional[AsyncIOMotorClientSession] = None
    ) -> Optional[ReadT]:
        if not obj_id:
            return None
        restored = await self.repo.restore_by_id(obj_id, session=session)
        if not restored:
            raise NotFoundError("对象不存在或无法恢复")
        await self.cache_repo.cache_detail(restored.model_dump())
        await self.cache_repo.delete_search_cache_all()
        return self.read_model(**restored.model_dump())
from functools import cache
from bson import ObjectId
from typing import List, Optional, Union, Dict, Any
from pymongo import ReturnDocument

from pydantic.v1.utils import Obj
from src.models import (
    CustomListType,
    CustomListInDB,
    CustomListCreate,
    CustomListUpdate,
    CustomListRead,
    CustomListPageResult,
    UserRole,
)
from src.repos import (
    UserCustomListRepo,
    UserCustomListRedisRepo,
)
from src.logic.base_logic import BaseLogic
from config.logging import get_logic_logger
from src.core.handler import logic_handler
from src.core.exceptions import ConflictError, ValidationError, NotFoundError


class CollectionLogic(BaseLogic[CustomListInDB, CustomListCreate, CustomListUpdate, CustomListRead]):
    def __init__(self):
        super().__init__(
            repo=UserCustomListRepo(),
            read_model=CustomListRead,
            cache_repo=UserCustomListRedisRepo(),
        )
        self.logger = get_logic_logger("collection_logic")

    # def __getattribute__(self, name):
    #     attr = super().__getattribute__(name)

    #     # 允许访问普通属性或私有变量
    #     if not callable(attr) or name.startswith("_"):
    #         return attr

    #     # 获取当前类定义的方法集合
    #     cls = type(self)
    #     current_methods = cls.__dict__.keys()

    #     # 若该方法不是当前类自己定义的（来自父类），禁止访问
    #     if name not in current_methods:
    #         raise AttributeError(f"禁止直接调用父类方法 '{name}'，请使用 LibraryLogic 提供的封装接口")

    #     return attr

    # ----------------------------- 选用的父类方法 -----------------------------

    @logic_handler("获取片单详情")
    async def get_collection(self, collection_id: str, session=None) -> CustomListRead:
        result = await super().get_by_id(collection_id, session=session)
        return result

    @logic_handler("创建片单")
    async def create_collection(
        self, payload: CustomListCreate, session=None
    ) -> CustomListRead:
        if payload.type in (CustomListType.FAVORITE, CustomListType.WATCHLIST):
            raise ValueError(f"用户已存在 {payload.type.value} 合集，唯一约束不允许重复创建")
        
        existed_by_name = await self.repo.exists({"name": payload.name, "user_id": ObjectId(payload.user_id)}, session=session)
        if existed_by_name:
            raise ConflictError("片单名已存在")
        created = await super().create(payload, session=session)
        return created

    @logic_handler("更新片单")
    async def update_collection(
        self, collection_id: str, collection_update: CustomListUpdate, session=None
    ) -> CustomListRead:
        collection = await self.get_collection(collection_id, session=session)
        if collection_update.name and collection_update.name != collection.name:
            existed_by_name = await self.repo.exists(
                {"name": collection_update.name, "_id": {"$ne": ObjectId(collection_id)}},
                session=session
            )
            if existed_by_name:
                raise ConflictError("片单名已存在")

        update_payload = collection_update.model_dump(exclude_unset=True)       
        updated = await super().update_by_id(collection_id, update_payload, session=session)
        return updated

    @logic_handler("删除片单")
    async def delete_collection(self, collection_id: str, session=None) -> bool:
        count = await super().delete_by_id(collection_id, soft_delete=False, session=session)
        return count > 0

    # ----------------------------- 子类特有方法 -----------------------------
    @logic_handler("获取用户的所有片单")
    async def get_user_collections(self, user_id: str, use_cache: bool = True, session=None) -> List[CustomListRead]:
        if use_cache:
            cached = await self.cache_repo._get_item_list('user', user_id)
            if cached and isinstance(cached, dict):
                # self.logger.info(f"get_user_collections {user_id} from cache: {cached.values()}")
                return cached.values()
        
        collections = await self.repo.find({"user_id": ObjectId(user_id)},session=session)
        # self.logger.info(f"get_user_collections {user_id} from db: {collections}")
        await self.cache_repo._cache_item_list('user', user_id, items=[v.model_dump() for v in collections])
        return collections


    @logic_handler("获取目标片单 + 待观看 + 收藏")
    async def get_target_collection_with_addtion_items(self, collection_id, user_id, session=None)->Dict[str, CustomListRead]:
        result = {}
        cached = await self.cache_repo._get_item_list('user', user_id)
        
        if not cached or not isinstance(cached, dict):
            collections = await self.get_user_collections(user_id, session=session)
            # self.logger.info(f"get_user_collections: {collections}")
        else:
            collections = cached.values()

        for v in collections:
            if v.type in (CustomListType.FAVORITE, CustomListType.WATCHLIST):
                result[v.type.value] = v
            if v.id == collection_id:
                result['target'] = v
        if CustomListType.FAVORITE.value not in result or CustomListType.WATCHLIST.value not in result:
            raise ValueError("用户收藏片单或观看片单不存在")

        if 'target' not in result:
            # 可能是其他用户的公共片单
            cached = await self.cache_repo.get_detail(collection_id)
            if cached:
                result['target'] = cached
            else:
                result['target'] = await self.repo.find_by_id(collection_id, session=session)
                await self.cache_repo.cache_detail(result['target'].model_dump())

        return result

    @logic_handler("初始化用户默认片单")
    async def init_default(self, user_id: str, session=None) -> List[CustomListRead]:
        favoriter = CustomListCreate(
                name="收藏",
                type=CustomListType.FAVORITE,
                description=f"{user_id}收藏的片单",
                is_public=False,
                movies=[],
                user_id=user_id,
            )
        watcher = CustomListCreate(
                name="观看",
                type=CustomListType.WATCHLIST,
                description=f"{user_id}观看的片单",
                is_public=False,
                movies=[],
                user_id=user_id,
            )
        created = await self.repo.insert_many([favoriter, watcher], session=session)
        return created

    @logic_handler("想指定片单中追加电影s")
    async def append_movies(
        self,
        collection_id: str,
        movie_ids: List[str],
        session=None,
    ) -> CustomListRead:
        movie_object_ids = [ObjectId(mid) for mid in movie_ids]
        
        # 使用 $addToSet 原子追加
        updated_doc = await self.repo.collection.find_one_and_update(
            {"_id": ObjectId(collection_id)},
            {"$addToSet": {"movies": {"$each": movie_object_ids}}},
            return_document=ReturnDocument.AFTER,
            session=session
        )
        
        if not updated_doc:
            raise NotFoundError(f"片单不存在: {collection_id}")
            
        # 转换为 Pydantic 模型
        updated_model = self.repo.convert_dict_to_pydanticModel([updated_doc])[0]
        
        # 更新详情缓存
        await self.cache_repo.cache_detail(updated_model.model_dump())
        await self.cache_repo.delete_search_cache_all()
        
        # 清除列表缓存 (UserCustomListRedisRepo 特有)
        await self.cache_repo.delete_item_list("user", str(updated_model.user_id))
        
        return self.read_model(**updated_model.model_dump())
    
    @logic_handler("向指定片单中删除电影s")
    async def remove_movies(
        self,
        collection_id: str,
        movie_ids: List[str],
        session=None,
    ) -> CustomListRead:
        movie_object_ids = [ObjectId(mid) for mid in movie_ids]
        
        # 使用 $pull 原子删除
        updated_doc = await self.repo.collection.find_one_and_update(
            {"_id": ObjectId(collection_id)},
            {"$pull": {"movies": {"$in": movie_object_ids}}},
            return_document=ReturnDocument.AFTER,
            session=session
        )
        
        if not updated_doc:
            raise NotFoundError(f"片单不存在: {collection_id}")
            
        # 转换为 Pydantic 模型
        updated_model = self.repo.convert_dict_to_pydanticModel([updated_doc])[0]
        
        # 更新详情缓存
        await self.cache_repo.cache_detail(updated_model.model_dump())
        await self.cache_repo.delete_search_cache_all()
        
        # 清除列表缓存
        await self.cache_repo.delete_item_list("user", str(updated_model.user_id))
        
        return self.read_model(**updated_model.model_dump())

    @logic_handler("同步脏集合（暂未实现 Write-Behind）")
    async def sync_dirty_collections_from_cache(self) -> Dict[str, Any]:
        """
        同步 Redis 中标记为脏的片单数据回 MongoDB。
        目前片单操作（append_movies/remove_movies）采用直写 DB + 更新 Cache 策略，
        暂无 Write-Behind 机制，故此方法目前仅作为占位符，防止定时任务报错。
        """
        # TODO: 实现 Write-Behind 机制后，在此处扫描脏集合并批量写回
        self.logger.info("sync_dirty_collections_from_cache: No dirty collection strategy implemented yet.")
        return {"synced_count": 0, "errors": []}

    # -------------------------- search Bar -----------------------------
    @logic_handler("查询用户合集列表")
    async def list_collections(
        self,
        user_id: str,
        role: UserRole,
        type_filter: Union[str, CustomListType, None] = None,
        only_me: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        query: Optional[str] = None,
        session=None,
    ) -> List[CustomListRead]:
        if role == UserRole.ADMIN and only_me and not user_id:
            raise ValidationError("管理员 only_me 模式需要提供 user_id")

        params = {k: v for k, v in locals().items() if k not in ("self", "session")}
        search_key = self._build_search_key(**params)
        cached = await self.cache_repo.get_search_page(search_key, page)
        if cached:
            return CustomListPageResult(**cached)

        addition_filter: Optional[Dict[str, Any]] = None
        user_id_for_repo: Optional[ObjectId] = None

        if role == UserRole.ADMIN:
            if only_me and user_id:
                addition_filter = {"user_id": ObjectId(user_id)}
            elif user_id:
                addition_filter = {"$or": [{"user_id": ObjectId(user_id)}, {"is_public": True}]}
            else:
                addition_filter = {}
        elif role == UserRole.USER:
            if only_me and user_id:
                addition_filter = {"user_id": ObjectId(user_id)}
            elif user_id:
                addition_filter = {"$or": [{"user_id": ObjectId(user_id)}, {"is_public": True}]}
        elif role == UserRole.GUEST:
            addition_filter = {"is_public": True}

        filter_dict: Dict[str, Any] = {}
        and_conditions: List[Dict[str, Any]] = []

        if query:
            text_fields = ["name", "description"]
            and_conditions.append({"$or": [{f: {"$regex": query, "$options": "i"}} for f in text_fields]})
        
        if type_filter:
            filter_dict["type"] = type_filter.value
        
        if addition_filter:
            # 安全合并 addition_filter，避免覆盖 $or
            if "$or" in addition_filter:
                and_conditions.append({"$or": addition_filter["$or"]})
                for k, v in addition_filter.items():
                    if k != "$or":
                        filter_dict[k] = v
            else:
                filter_dict.update(addition_filter)
        
        if and_conditions:
            filter_dict["$and"] = and_conditions

        skip = max(page - 1, 0) * page_size
        results = await self.repo.find(
            filter_dict,
            skip=skip,
            limit=page_size,
            session=session,
        )
        total = await self.repo.count(filter_dict, session=session)
        pages = (total + page_size - 1) // page_size

        page_result = CustomListPageResult(
            items=results, total=total, page=page, size=page_size, pages=pages
        )
        await self.cache_repo.cache_search_page(search_key, page, page_result.model_dump())
        return page_result


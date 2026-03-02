from bson import ObjectId
from typing import Any, Dict, Optional, List, Union, Tuple

from config.logging import get_logic_logger
from src.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from src.core.handler import logic_handler
from src.models import (
    LibraryCreate,
    LibraryPageResult,
    LibraryRead,
    LibraryType,
    LibraryUpdate,
    LibraryInDB,
)
from src.models import UserRole
from src.logic.base_logic import BaseLogic
from src.repos import LibraryRepo
from src.repos import LibraryRedisRepo, UserRedisRepo


class LibraryLogic(BaseLogic[LibraryInDB, LibraryCreate, LibraryUpdate, LibraryRead]):
    def __init__(self):
        super().__init__(
            repo=LibraryRepo(),
            read_model=LibraryRead,
            cache_repo=LibraryRedisRepo(),
        )
        self.user_cache_repo = UserRedisRepo()
        self.logger = get_logic_logger("library_logic")

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

    @logic_handler("获取媒体库详情")
    async def get_library(self, library_id: str, session=None) -> LibraryRead:
        result = await super().get_by_id(library_id, session=session)
        return result

    @logic_handler("创建媒体库")
    async def create_library(
        self, payload: LibraryCreate, session=None
    ) -> LibraryRead:
        existed_by_name = await self.repo.exists({"name": payload.name}, session=session)
        if existed_by_name:
            raise ConflictError("库名已存在")
        created = await super().create(payload, session=session)
        return created

    @logic_handler("更新媒体库")
    async def update_library(
        self, library_id: str, library_update: LibraryUpdate, session=None
    ) -> LibraryRead:
        library = await self.get_library(library_id, session=session)
        if library.is_deleted:
            raise ConflictError("已删除的库不能更新")

        if library_update.name and library_update.name != library.name:
            existed_by_name = await self.repo.exists(
                {"name": library_update.name, "_id": {"$ne": ObjectId(library_id)}},
                session=session
            )
            if existed_by_name:
                raise ConflictError("库名已存在")

        update_payload = library_update.model_dump(exclude_unset=True)
        updated = await super().update_by_id(library_id, update_payload, session=session)
        return updated

    @logic_handler("删除媒体库")
    async def delete_library(
        self, library_id: str, soft_delete: bool = True, session=None
    ) -> bool:
        count = await super().delete_by_id(library_id, soft_delete=soft_delete, session=session)
        return count > 0

    @logic_handler("恢复媒体库")
    async def restore_library(self, library_id: str, session=None) -> LibraryRead:
        library = await self.get_library(library_id, session=session)
        if not library.is_deleted:
            return library
        restored = await super().restore_by_id(library_id, session=session)
        return restored

    # ----------------------------- 子类特有方法 -----------------------------
    # -------------------------- 进入/退出/查询 当前库-------------------------
    @logic_handler("进入库")
    async def enter_library(
        self, library_id: str, user_id: str, session=None
    ) -> LibraryRead:
        library = await self.get_library(library_id, session=session)
        if library.is_deleted:
            raise ValidationError("库已被删除，无法进入")
        if not library.is_active:
            raise ValidationError("库已停用，无法进入")
        await self.user_cache_repo.set_current_library(user_id, library.model_dump(), expire=86400)
        return library

    @logic_handler("退出库")
    async def exit_library(self, user_id: str, session=None) -> bool:
        deleted_count = await self.user_cache_repo.delete_current_library(user_id)
        return deleted_count > 0

    @logic_handler("获取当前库")
    async def get_current_library(self, user_id: str) -> Optional[LibraryRead]:
        library_data = await self.user_cache_repo.get_current_library(user_id)
        return LibraryRead(**library_data) if library_data else None

    @logic_handler("清理用户库缓存")
    async def clear_user_library_cache(self, user_id: str) -> bool:
        return await self.exit_library(user_id)

    # -------------------------- 特殊更新 -----------------------------
    @logic_handler("更新媒体库的根路径")
    async def update_library_root_path(
        self, library_id: str, root_path: str, session=None
    ) -> LibraryRead:
        updated = await super().update_by_id(library_id, {"root_path": root_path}, session=session)
        return updated

    @logic_handler("更新媒体库活跃状态")
    async def update_library_activity(
        self, library_id: str, is_active: bool, session=None
    ) -> LibraryRead:
        library = await self.get_library(library_id, session=session)
        if library.is_deleted:
            raise ConflictError("已删除的库不能更新活跃状态")
        if library.is_active == is_active:
            return library

        updated = await super().update_by_id(library_id, {"is_active": is_active}, session=session)
        return updated

    @logic_handler("更新媒体库可见性")
    async def update_library_visibility(
        self, library_id: str, is_public: bool, session=None
    ) -> LibraryRead:
        library = await self.get_library(library_id, session=session)
        if library.is_deleted:
            raise ConflictError("已删除的库不能更新可见性")
        if library.is_public == is_public:
            return library

        updated = await super().update_by_id(library_id, {"is_public": is_public}, session=session)
        return updated

    # -------------------------- search Bar -----------------------------

    @logic_handler("获取媒体库列表")
    async def list_libraries(
        self,
        role: UserRole,
        user_id: Optional[str] = None,
        only_me: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
        library_type: Optional[LibraryType] = None,
        is_active: Optional[bool] = None,
        is_deleted: Optional[bool] = None,
        auto_import: Optional[bool] = None,
        query: Optional[str] = None,
        session=None,
    ) -> LibraryPageResult:
        if role == UserRole.ADMIN and only_me and not user_id:
            raise ValidationError("管理员 only_me 模式需要提供 user_id")

        params = {k: v for k, v in locals().items() if k not in ("self", "session")}
        search_key = self._build_search_key(**params)
        cached = await self.cache_repo.get_search_page(search_key, page)
        if cached:
            return LibraryPageResult(**cached)

        addition_filter: Optional[Dict[str, Any]] = None
        user_id_for_repo: Optional[ObjectId] = None

        if role == UserRole.ADMIN:
            user_id_for_repo = ObjectId(user_id) if only_me and user_id else None
        elif role == UserRole.USER:
            if only_me and user_id:
                # Support both String and ObjectId user_id for robustness (especially in tests vs prod)
                try:
                    user_oid = ObjectId(user_id)
                    addition_filter = {"$or": [{"user_id": user_id}, {"user_id": user_oid}]}
                except:
                    addition_filter = {"user_id": user_id}
            elif user_id:
                addition_filter = {"$or": [{"user_id": ObjectId(user_id)}, {"is_public": True}]}
        elif role == UserRole.GUEST:
            addition_filter = {"is_public": True}

        filter_dict: Dict[str, Any] = {}
        and_conditions: List[Dict[str, Any]] = []

        if query:
            text_fields = ["name", "description", "root_path"]
            and_conditions.append({"$or": [{f: {"$regex": query, "$options": "i"}} for f in text_fields]})
        
        if library_type:
            filter_dict["type"] = library_type.value
        if user_id_for_repo is not None:
            filter_dict["user_id"] = user_id_for_repo
        if is_active is not None:
            filter_dict["is_active"] = is_active
        if is_deleted is not None:
            filter_dict["is_deleted"] = is_deleted
        if auto_import is not None:
            filter_dict["auto_import"] = auto_import
        
        if addition_filter:
            # 安全合并 addition_filter，避免覆盖 $or，否则搜索关键词的 $or 条件被权限过滤器的 $or 条件覆盖 。因此，无论输入什么，系统实际上都在执行“查询所有我有权限看到的库/片单”
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

        page_result = LibraryPageResult(
            items=results, total=total, page=page, size=page_size, pages=pages
        )
        await self.cache_repo.cache_search_page(search_key, page, page_result.model_dump())
        return page_result

    # -------------------------- 统计信息 -----------------------------
    @logic_handler("获取媒体库统计信息")
    async def get_library_stats(self, library_id: str, session=None) -> Dict[str, Any]:
        _ = await self.get_library(library_id, session=session)
        pipeline = [
            {"$match": {"_id": ObjectId(library_id), "is_deleted": False}},
            {
                "$lookup": {
                    "from": "movies",
                    "localField": "_id",
                    "foreignField": "library_id",
                    "as": "movies",
                }
            },
            {
                "$lookup": {
                    "from": "assets",
                    "localField": "movies._id",
                    "foreignField": "movie_id",
                    "as": "assets",
                }
            },
            {
                "$project": {
                    "name": 1,
                    "type": 1,
                    "is_active": 1,
                    "total_movies": {"$size": "$movies"},
                    "total_assets": {"$size": "$assets"},
                    "last_scan": 1,
                    "created_at": 1,
                }
            },
        ]
        result = await self.repo.aggregate(pipeline, session=session)
        return result[0] if result else {}

    async def get_libraries_stats(
        self, user_id: str, session=None
    ) -> Dict[str, Any]:
        pipeline = [
            {"$match": {"is_deleted": False, "user_id": ObjectId(user_id)}},
            {
                "$group": {
                    "_id": None,
                    "total_libraries": {"$sum": 1},
                    "active_libraries": {"$sum": {"$cond": ["$is_active", 1, 0]}},
                    "inactive_libraries": {
                        "$sum": {"$cond": [{"$eq": ["$is_active", False]}, 1, 0]}
                    },
                    "movie_libraries": {
                        "$sum": {"$cond": [{"$eq": ["$type", "movie"]}, 1, 0]}
                    },
                    "tv_libraries": {
                        "$sum": {"$cond": [{"$eq": ["$type", "tv"]}, 1, 0]}
                    },
                }
            },
        ]
        result = await self.repo.aggregate(pipeline, session=session)
        return result[0] if result else {}


    # -------------------------- 后续拓展 -----------------------------
    @logic_handler("扫描媒体库")
    async def scan_library(self, library_id: str, session=None) -> Dict[str, Any]:
        raise BadRequestError("扫描库未实现")

    @logic_handler("获取用户可访问库ID列表")
    async def list_accessible_library_ids(
        self,
        role: UserRole,
        user_id: Optional[str] = None,
        session=None,
    ) -> List[str]:
        addition_filter: Optional[Dict[str, Any]] = None
        user_id_for_repo: Optional[ObjectId] = None

        if role == UserRole.ADMIN:
            user_id_for_repo = ObjectId(user_id) if user_id else None
        elif role == UserRole.USER:
            if user_id:
                addition_filter = {"$or": [{"user_id": ObjectId(user_id)}, {"is_public": True}]}
        elif role == UserRole.GUEST:
            addition_filter = {"is_public": True}

        filter_dict: Dict[str, Any] = {}
        if user_id_for_repo is not None:
            filter_dict["user_id"] = user_id_for_repo
        if addition_filter:
            filter_dict.update(addition_filter)

        results = await self.repo.find(
            filter_dict,
            projection={"_id": 1},
            session=session,
        )
        return [str(doc["_id"]) for doc in results]

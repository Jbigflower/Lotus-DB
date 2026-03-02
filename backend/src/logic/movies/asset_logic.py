from bson import ObjectId
from typing import Optional, List, Dict, Any
from src.repos import AssetRepo
from src.models import (
    AssetCreate,
    AssetUpdate,
    AssetRead,
    AssetType,
    AssetStoreType,
    AssetInDB,
    AssetPageResult,
)
from src.logic.base_logic import BaseLogic
from src.repos.cache_repos.asset_redis_repo import AssetRedisRepo
from src.core.handler import logic_handler
from config.logging import get_logic_logger


class MovieAssetLogic(BaseLogic[AssetInDB, AssetCreate, AssetUpdate, AssetRead]):
    """
    电影逻辑层
    批处理 + 单例 混合使用
    """

    def __init__(self):
        super().__init__(
            repo=AssetRepo(),
            read_model=AssetRead,
            cache_repo=AssetRedisRepo(),
        )
        # 保持原有逻辑层 logger 命名
        self.logger = get_logic_logger("asset_logic")

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
    @logic_handler("查询资产详情")
    async def get_asset(self, asset_id: str, session=None) -> AssetRead:
        result = await super().get_by_id(asset_id, session=session)
        return result

    @logic_handler("查询多个资产详情")
    async def get_assets(self, asset_ids: List[str], session=None) -> List[AssetRead]:
        result = await super().get_by_ids(asset_ids, session=session)
        return result

    @logic_handler("从路径创建资产")
    async def create_asset(
        self,
        payload: AssetCreate,
        session=None,
    ) -> AssetRead:
        created = await super().create(payload, session=session)
        # 缓存清理：电影资产列表
        await self.cache_repo.delete_item_list("movie", payload.movie_id)
        return created

    @logic_handler("更新资产")
    async def update_asset(
        self, asset_id: str, update_payload: Dict[str, Any], session=None
    ) -> AssetRead:
        updated = await super().update_by_id(asset_id, update_payload, session=session)
        return updated

    @logic_handler("删除单个资产")
    async def delete_asset(self, asset_id: str, *, soft_delete: bool = True, session=None) -> bool:
        # 获取资产信息以便知道属于哪个 movie_id
        asset = await self.repo.find_by_id(asset_id)
        result = await super().delete_by_id(asset_id, soft_delete=soft_delete, session=session)
        if asset and asset.movie_id:
            # 缓存清理：电影资产列表
            await self.cache_repo.delete_item_list("movie", asset.movie_id) 
        return result

    @logic_handler("删除多个资产")
    async def delete_assets(self, asset_ids: List[str], *, soft_delete: bool = False, session=None) -> int:
        # 获取资产信息以便知道属于哪个 movie_id
        assets = await self.repo.find_by_ids(asset_ids)
        result = await super().deleted_by_ids(asset_ids, soft_delete=soft_delete, session=session)
        # 缓存清理：电影资产列表
        for asset in assets or []:
            if asset.movie_id:
                await self.cache_repo.delete_item_list("movie", asset.movie_id)     
        return result

    @logic_handler("恢复单个资产")
    async def restore_asset(self, asset_id: str, session=None) -> bool:
        result = await super().restore_by_id(asset_id, session=session)
        if asset and asset.movie_id:
            # 缓存清理：电影资产列表
            await self.cache_repo.delete_item_list("movie", asset.movie_id) 
        return result
    
    @logic_handler("恢复多个资产")
    async def restore_assets(self, asset_ids: List[str], session=None) -> dict:
        result = await super().restore_by_ids(asset_ids, session=session)
        # 缓存清理：电影资产列表
        for asset_id in asset_ids or []:
            asset = await self.repo.find_by_id(asset_id)
            if asset and asset.movie_id:
                await self.cache_repo.delete_item_list("movie", asset.movie_id) 
        return result

    # ----------------------------- 子类特有方法 -----------------------------
    # --------------------------  协同方法： Movie  --------------------------
    @logic_handler("获取多个电影的所有资产")
    async def list_movies_assets(self, movie_ids: List[str], session=None) -> Dict[str, List[AssetRead]]:
        """
        获取多个电影的所有资产，返回一个字典，键为电影ID，值为资产列表
        """
        asset_dict = {}
        missing_mids = []
        for movie_id in movie_ids:
            cached_list = await self.cache_repo._get_item_list("movie", movie_id)
            if cached_list:
                try:
                    asset_dict[movie_id] = [AssetRead(**item) for item in cached_list]
                except Exception as e:
                    self.logger.error(f"缓存数据转换失败: {e}")
                    missing_mids.append(movie_id)
            else:
                missing_mids.append(movie_id)
        
        # 从数据库读取（若缓存不存在
        if missing_mids:
            results = await self.repo.find({"movie_id": {"$in": [ObjectId(mid) for mid in missing_mids]}}, session=session)
            for mid in missing_mids:
                asset_dict[mid] = [AssetRead(**r.model_dump()) for r in results if r.movie_id == mid]
                await self.cache_repo._cache_item_list("movie", mid, asset_dict[mid])

        return asset_dict

    @logic_handler("删除电影中所有资产")
    async def delete_movies_assets(
        self, movie_ids: List[str], soft_delete: bool = True, session=None
    ):
        """
        删除多个电影的所有资产
        """
        asset_ids = await self.repo.find({"movie_id": {"$in": [ObjectId(mid) for mid in movie_ids]}}, projection={"_id": 1}, session=session)
        asset_ids = [str(asset.id) for asset in asset_ids]
        count = await self.repo.delete_many({"movie_id": {"$in": [ObjectId(mid) for mid in movie_ids]}}, soft_delete=soft_delete, session=session)

        await self.cache_repo.delete_details_batch(asset_ids)
        await self.cache_repo.delete_search_cache_all()
        for mid in movie_ids:
            await self.cache_repo.delete_item_list("movie", mid)
        return count

    @logic_handler("删除库中的所有资产")
    async def delete_library_assets(
        self,
        library_id: str,
        movie_ids: list[str],
        soft_delete: bool = True,
        session=None,
    ):
        asset_ids = await self.repo.find({"library_id": ObjectId(library_id)}, projection={"_id": 1}, session=session)
        asset_ids = [str(asset.id) for asset in asset_ids]
        
        count = await self.repo.delete_by_ids(asset_ids, soft_delete=soft_delete, session=session)
        await self.cache_repo.delete_details_batch(asset_ids)
        await self.cache_repo.delete_search_cache_all()
        for movie_id in movie_ids:
            await self.cache_repo.delete_item_list("movie", movie_id)
        return count

    # -------------------------- search Bar -----------------------------
    @logic_handler("综合搜索资源")
    async def search_assets(
        self,
        query: Optional[str] = None,
        movie_id: Optional[str] = None,
        asset_type: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        min_duration: Optional[int] = None,
        max_duration: Optional[int] = None,
        addition_filter: Optional[Dict[str, Any]] = None,
        page: int = 1,
        size: int = 20,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, int]] = None,
        session=None,
        is_deleted: Optional[bool] = False,
        library_ids: Optional[List[str]] = None,
    ):
        params = {k: v for k, v in locals().items() if k not in ("self", "session")}
        search_key = self._build_search_key(**params)
        cached = await self.cache_repo.get_search_page(search_key, page)
        self.logger.info(f"缓存搜索结果: {cached}")
        if cached:
            items = [AssetRead(**item) for item in cached.get("items", [])]
            return AssetPageResult(
                total=cached.get("total", len(items)),
                page=cached.get("page", page),
                size=cached.get("size", len(items)),
                items=items,
            )

        filter_dict: Dict[str, Any] = {}

        if query:
            text_fields = ["name", "path", "metadata.quality", "metadata.codec"]
            filter_dict["$or"] = [{f: {"$regex": query, "$options": "i"}} for f in text_fields]

        if movie_id:
            filter_dict["movie_id"] = ObjectId(movie_id)
        if asset_type:
            filter_dict["type"] = asset_type
        
        if is_deleted is not None:
            filter_dict["is_deleted"] = is_deleted

        if library_ids:
            filter_dict["library_id"] = {"$in": [ObjectId(lid) for lid in library_ids]}

        if min_size is not None or max_size is not None:
            size_cond: Dict[str, Any] = {}
            if min_size is not None:
                size_cond["$gte"] = min_size
            if max_size is not None:
                size_cond["$lte"] = max_size
            filter_dict["metadata.size"] = size_cond

        if min_duration is not None or max_duration is not None:
            duration_cond: Dict[str, Any] = {}
            if min_duration is not None:
                duration_cond["$gte"] = min_duration
            if max_duration is not None:
                duration_cond["$lte"] = max_duration
            filter_dict["metadata.duration"] = duration_cond

        if addition_filter:
            # 安全合并 addition_filter，避免覆盖 $or
            if "$or" in addition_filter:
                if "$or" not in filter_dict:
                    filter_dict["$or"] = []
                # 注意：这里如果 filter_dict 已经有 $or，直接 extend 可能会导致逻辑变成 (A or B) and (C or D) 还是 (A or B or C or D)?
                # MongoDB 的 filter_dict["$or"] 是一个列表，表示满足其中任意一个。
                # 如果我们要实现 (Query match) AND (Permission match)，我们需要用 $and
                # 原有的代码逻辑是 filter_dict.update(addition_filter)，这会直接覆盖 $or
                
                # 正确的做法是：
                # 如果 filter_dict 已经有 $or (来自 query)，我们需要将 query 的 $or 和 addition_filter 的 $or 用 $and 连接
                # 或者将它们放入 $and 列表
                
                # 为了保持与 movie_logic 一致的 safe merge 模式，我们应该重构 query 的处理方式
                # 但为了最小化改动，我们可以这样做：
                
                existing_or = filter_dict.pop("$or", None)
                and_list = []
                if existing_or:
                    and_list.append({"$or": existing_or})
                
                and_list.append({"$or": addition_filter["$or"]})
                
                for k, v in addition_filter.items():
                    if k != "$or":
                        filter_dict[k] = v
                
                if "$and" not in filter_dict:
                    filter_dict["$and"] = []
                filter_dict["$and"].extend(and_list)

            else:
                filter_dict.update(addition_filter)

        skip = max(page - 1, 0) * size
        self.logger.info(f"查询资产: {filter_dict}")
        results = await self.repo.find(
            filter_dict,
            skip=skip,
            limit=size,
            sort=sort,
            projection=projection,
            session=session,
        )
        self.logger.info(f"查询资产结果: {results}")
        total = await self.repo.count(filter_dict, session=session)
        pages = (total + size - 1) // size

        items = [AssetRead(**asset.model_dump()) for asset in results]
        page_result = AssetPageResult(items=items, total=total, page=page, size=size, pages=pages)
        await self.cache_repo.cache_search_page(search_key, page, page_result.model_dump())
        return page_result
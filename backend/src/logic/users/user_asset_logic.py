# 顶部导入更新（替换/补充依赖）
# AssetLogic
from typing import Optional, Dict, Any, List, Tuple, Set

from bson import ObjectId
from pymongo import UpdateOne
from pymongo.errors import PyMongoError
from src.repos import UserAssetRepo, UserAssetRedisRepo
from src.logic.base_logic import BaseLogic
from src.models import (
    PartialPageResult,
    UserAssetType,
    UserAssetInDB,
    UserAssetCreate,
    UserAssetUpdate,
    UserAssetPageResult,
    UserAssetRead,
)
from config.logging import get_logic_logger
from src.core.handler import logic_handler
from src.core.exceptions import (
    NotFoundError,
    BaseRepoException,
)

class UserAssetLogic(BaseLogic[UserAssetInDB, UserAssetCreate, UserAssetUpdate, UserAssetRead]):
    """
    用户资产逻辑层
    批处理 + 单例 混合使用
    """

    def __init__(self):
        super().__init__(
            repo=UserAssetRepo(),
            read_model=UserAssetRead,
            cache_repo=UserAssetRedisRepo(),
        )
        # 保持原有逻辑层 logger 命名
        self.logger = get_logic_logger("user_asset_logic")

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
    async def get_asset(self, asset_id: str, session=None) -> UserAssetRead:
        result = await super().get_by_id(asset_id, session=session)
        return result   

    @logic_handler("查询多个资产详情")
    async def get_assets(self, asset_ids: List[str], session=None) -> List[UserAssetRead]:
        result = await super().get_by_ids(asset_ids, session=session)
        return result

    @logic_handler("从路径创建资产")
    async def create_asset(
        self,
        payload: UserAssetCreate,
        session=None,
    ) -> UserAssetRead:
        created = await super().create(payload, session=session)
        return created

    @logic_handler("创建多个资产")
    async def create_assets(
        self, data: List[UserAssetCreate], session=None
    ) -> List[UserAssetRead]:
        """创建多个资产，一般不会调用，除非是批量导入截图"""
        results = await super().create_batch(data, session=session)
        return results

    @logic_handler("更新资产")
    async def update_asset(
        self, asset_id: str, update_payload: Dict[str, Any], session=None
    ) -> UserAssetRead:
        updated = await super().update_by_id(asset_id, update_payload, session=session)
        return updated

    @logic_handler("删除单个资产")
    async def delete_asset(self, asset_id: str, *, soft_delete: bool = True, session=None) -> bool:
        result = await super().delete_by_id(asset_id, soft_delete=soft_delete, session=session)
        return result

    @logic_handler("删除多个资产")
    async def delete_assets(self, asset_ids: List[str], *, soft_delete: bool = False, session=None) -> dict:
        result = await super().deleted_by_ids(asset_ids, soft_delete=soft_delete, session=session)
        return result

    @logic_handler("恢复单个资产")
    async def restore_asset(self, asset_id: str, session=None) -> bool:
        result = await super().restore_by_id(asset_id, session=session)
        return result
    
    @logic_handler("恢复多个资产")
    async def restore_assets(self, asset_ids: List[str], session=None) -> dict:
        result = await super().restore_by_ids(asset_ids, session=session)
        return result

    # ----------------------------- 子类特有方法 -----------------------------
    # -------------------------- search Bar -----------------------------
    @logic_handler("分页查询用户资产")
    async def list_assets(
        self,
        query: Optional[str],
        user_id: Optional[str],
        movie_ids: Optional[List[str]],
        asset_type: List[Optional[UserAssetType]],
        tags: Optional[List[str]],
        is_public: Optional[bool],
        page: int,
        size: int,
        sort: Optional[List[Tuple[str, int]]],
        projection: Optional[Dict[str, int]] = None,
        session=None,
        is_deleted: Optional[bool] = False,
    ) -> [PartialPageResult | UserAssetPageResult]:
        # 构建过滤条件（迁移自 Repo.search_assets）
        filter_dict: Dict[str, Any] = {}
        text_fields = [
            "name",
            "content", # 支持内容检索
            "tags",    # 支持标签检索
        ]
        if query and text_fields:
            filter_dict["$or"] = [
                {f: {"$regex": query, "$options": "i"}} for f in text_fields
            ]
        if user_id:
            filter_dict["user_id"] = ObjectId(user_id)
        if movie_ids:
            if len(movie_ids) == 1:
                filter_dict["movie_id"] = ObjectId(movie_ids[0])
            else:
                filter_dict["movie_id"] = {"$in": [ObjectId(id) for id in movie_ids]}
        if asset_type:
            valid_types = [t for t in asset_type if t is not None]
            if valid_types:
                if len(valid_types) > 1:
                    filter_dict["type"] = {"$in": [t.value for t in valid_types]}
                else:
                    filter_dict["type"] = valid_types[0].value
        if tags:
            filter_dict["tags"] = {"$in": tags}
        if is_public is not None:
            filter_dict["is_public"] = is_public
        
        # 增加软删除过滤
        if is_deleted is not None:
            filter_dict["is_deleted"] = is_deleted

        skip = max(page - 1, 0) * size

        results = await self.repo.find(
            filter_dict,
            skip=skip,
            limit=size,
            sort=sort,
            projection=projection,
            session=session,
        )
        total = await self.repo.count(filter_dict, session=session)
        pages = (total + size - 1) // size

        if projection is not None:
            return PartialPageResult(items=results, total=total, page=page, size=size, pages=pages)

        items = [UserAssetRead(**asset.model_dump()) for asset in results]
        return UserAssetPageResult(items=items, total=total, page=page, size=size, pages=pages)

    # -------------------------- 特殊更新 -----------------------------
    @logic_handler("设置资产公开状态")
    async def update_user_assets_activity(
        self, asset_ids: List[str], is_public: bool, session=None
    ) -> List[UserAssetRead]:
        update_data = {"is_public": is_public}
        return await super().update_by_ids(asset_ids, update_data, session=session)        

    # -------------------------- 特殊动作，电影资产的级联删除操作 -----------------------------
    @logic_handler("保存电影快照")
    async def save_movie_snapshot(
        self, snapshots: List[Dict[str, Any]], session=None
    ) -> None:
        if not snapshots:
            return None

        bulk_ops = [
            UpdateOne(
                {"movie_id": ObjectId(doc["id"])},
                {"$set": {"movie_snapshot": doc["snapshot"], "require_allocate": True}},
            )
            for doc in snapshots
        ]
        try:
            _ = await self.repo.collection.bulk_write(bulk_ops, ordered=False, session=session)
            return None
        except PyMongoError as e:
            raise BaseRepoException(f"批量更新快照失败: {e}") from e

    @logic_handler("获取所有的孤立资产")
    async def list_isolated_assets(
        self, user_id: str = None, session=None
    ) -> List[UserAssetRead]:
        """获取所有的孤立资产，分批拉取，每批 1000 条，使用 id 加速 skip"""
        filter_dict = {"require_allocate": True}
        if user_id:
            filter_dict["user_id"] = ObjectId(user_id)
        batch_size = self.repo.MAX_FIND_LIMIT
        all_assets: List[UserAssetRead] = []

        # 先统计总数
        total = await self.repo.count(filter_dict, session=session)
        if total == 0:
            return all_assets

        last_id = None
        while True:
            # 使用 last_id 加速 skip 的分页查询
            batch = await self.repo.find(
                filter_dict,
                sort=[("_id", 1)],
                limit=batch_size,
                last_id=last_id,
                session=session,
            )
            if not batch:
                break
            all_assets.extend([UserAssetRead(**asset.model_dump()) for asset in batch])
            if len(batch) < batch_size:
                break
            last_id = batch[-1].id

        return all_assets

    @logic_handler("重分配资产")
    async def allocate_assets(
        self, allocate_map: Dict[str, List], session=None
    ) -> None:
        """重分配资产
        :params allocate_map key Movie-id ｜ Value Asset-ids
        """
        if not allocate_map:
            return None

        bulk_ops = []
        for mid, asset_ids in allocate_map.items():
            bulk_ops.append(
                UpdateOne(
                    {"_id": {"$in": [ObjectId(aid) for aid in asset_ids]}},
                    {
                        "$set": {
                            "movie_snapshot": None,
                            "require_allocate": False,
                            "movie_id": ObjectId(mid),
                        }
                    },
                )
            )
        try:
            _ = await self.repo.collection.bulk_write(bulk_ops, ordered=False, session=session)
            return None
        except PyMongoError as e:
            raise BaseRepoException(f"批量重分配失败: {e}") from e
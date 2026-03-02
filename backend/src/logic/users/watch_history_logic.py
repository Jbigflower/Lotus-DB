
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import ReturnDocument
from src.repos import WatchHistoryRepo
from src.repos.cache_repos.watch_history_redis_repo import WatchHistoryRedisRepo
from src.models import (
    WatchHistoryRead,
    WatchHistoryPageResult,
    WatchHistoryInDB,
    WatchHistoryCreate,
    WatchHistoryUpdate,
    WatchType,
)
from src.logic.base_logic import BaseLogic
from src.core.exceptions import ConflictError, ValidationError
from src.core.handler import logic_handler
from config.logging import get_logic_logger


class WatchHistoryLogic(BaseLogic[WatchHistoryInDB, WatchHistoryCreate, WatchHistoryUpdate, WatchHistoryRead]):
    """
    用户观看历史逻辑层
    批处理 + 单例 混合使用
    """

    def __init__(self):
        super().__init__(
            repo=WatchHistoryRepo(),
            read_model=WatchHistoryRead,
            cache_repo=WatchHistoryRedisRepo(),
        )
        # 保持原有逻辑层 logger 命名
        self.logger = get_logic_logger("watch_history_logic")

    # ----------------------------- 选用的父类方法 -----------------------------
    @logic_handler("获取用户观看历史详情")
    async def get_watch_history(self, watch_history_id: str, session=None) -> WatchHistoryRead:
        result = await super().get_by_id(watch_history_id, session=session)
        return result

    @logic_handler("获取多条用户播放历史")
    async def get_watch_histories(self, watch_history_ids: List[str], session=None) -> List[WatchHistoryRead]:
        results = await super().get_by_ids(watch_history_ids, session=session)
        return results

    @logic_handler("创建用户观看历史")
    async def create_watch_history(self, payload: WatchHistoryCreate, session=None) -> WatchHistoryRead:
        # 检查用户是否已存在该媒体的观看历史
        existed_by_user_id = await self.repo.exists(
            {"user_id": ObjectId(payload.user_id), "asset_id": ObjectId(payload.asset_id)}, session=session
        )
        if existed_by_user_id:
            raise ConflictError("用户已存在该媒体的观看历史")
        created = await super().create(payload, session=session)
        await self.cache_repo._update_recent_list(payload.user_id, created.model_dump())
        return created

    @logic_handler("更新用户观看历史")
    async def update_watch_history(self, watch_history_id: str, watch_history_update: WatchHistoryUpdate, session=None) -> WatchHistoryRead:
        watch_history_update_dict = watch_history_update.model_dump(exclude_unset=True)
        if not watch_history_update_dict:
            raise ValidationError("更新数据不能为空")
        update = await super().update_by_id(watch_history_id, watch_history_update_dict, session=session)
        await self.cache_repo._update_recent_list(update.user_id, update.model_dump())
        return update

    @logic_handler("删除用户观看历史")
    async def delete_watch_history(self, watch_history_id: str, user_id, session=None) -> bool:
        delete_count = await super().delete_by_id(watch_history_id, session=session)
        if delete_count > 0:
            await self.cache_repo._delete_recent_list(user_id)
        return delete_count > 0

    @logic_handler("删除多条用户观看历史")
    async def delete_watch_historise(self, watch_history_ids: List[str], user_id, session=None) ->int:
        delete_count = await super().deleted_by_ids(watch_history_ids, soft_delete=False, session=session)
        if delete_count > 0:
            await self.cache_repo._delete_recent_list(user_id)
        return delete_count

    # ----------------------------- 子类特有方法 -----------------------------
    # ----------------------------- 观看进度原子更新 -----------------------------
    @logic_handler("Upsert 观看进度")
    async def upsert_watch_progress(
        self,
        user_id: str,
        asset_id: str,
        watch_type: WatchType,
        patch: Dict[str, Any],
        session=None,
    ) -> WatchHistoryRead:
        """
        原子化更新观看进度 (Upsert + 单调更新)
        :param patch: 包含 last_position, inc_watch 等字段
        """
        now = datetime.now(timezone.utc)
        
        filter_query = {
            "user_id": ObjectId(user_id),
            "asset_id": ObjectId(asset_id),
            "type": watch_type.value
        }
        
        # 准备 $set 字段 (排除特殊处理字段)
        set_fields = {
            "last_watched": now,
            **{k: v for k, v in patch.items() if k not in ("last_position", "watch_count", "inc_watch")}
        }
        
        # 准备 $setOnInsert 字段 (仅插入时生效)
        set_on_insert = {
            "user_id": ObjectId(user_id),
            "asset_id": ObjectId(asset_id),
            "type": watch_type.value,
            "created_at": now,
        }
        
        # 构建 Update Doc
        # $max: last_position 保证单调递增
        # $inc: watch_count 保证并发计数正确
        update_doc = {
            "$set": set_fields,
            "$setOnInsert": set_on_insert,
            "$max": {"last_position": patch.get("last_position", 0)},
            "$inc": {"watch_count": int(patch.get("inc_watch", 0))}
        }
        
        # 原子 Upsert
        result_doc = await self.repo.collection.find_one_and_update(
            filter_query,
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER,
            session=session
        )
        
        # 转换模型
        model = self.repo.convert_dict_to_pydanticModel([result_doc])[0]
        
        # 更新缓存
        await self.cache_repo.cache_detail(model.model_dump())
        await self.cache_repo._update_recent_list(user_id, model.model_dump())
        
        return self.read_model(**model.model_dump())

    # ----------------------------- 最近观看页面 -----------------------------
    @logic_handler("获取最近观看记录")
    async def get_recent_watch_histories(
        self, user_id: str, limit: int = 50, session=None
    ) -> List[WatchHistoryRead]:
        cached = await self.cache_repo._get_recent_list(user_id, limit=limit)
        if cached is not None:
            return cached
        page_result = await self.get_user_watch_histories(
            user_id=user_id, page=1, size=limit, session=session
        )
        await self.cache_repo._cache_recent_list(
            user_id, limit, page_result.items
        )
        return page_result.items

    # -------------------------- search Bar -----------------------------
    @logic_handler("获取用户观看历史列表")
    async def get_user_watch_histories(
        self,
        user_id: str,
        movie_ids: Optional[List[str]] = None,
        watch_type: Optional[WatchType] = None,
        finished: Optional[bool] = None,
        min_watch_times: Optional[int] = None,
        max_watch_times: Optional[int] = None,
        last_watched_after: Optional[datetime] = None,
        page: int = 1,
        size: int = 20,
        session=None,
    ) -> WatchHistoryPageResult:
        filter_dict: Dict[str, Any] = {"user_id": ObjectId(user_id)}
        if movie_ids:
            if len(movie_ids) == 1:
                filter_dict["movie_id"] = ObjectId(movie_ids[0])
            else:
                filter_dict["movie_id"] = {"$in": [ObjectId(mid) for mid in movie_ids]}
        if watch_type:
            filter_dict["type"] = watch_type.value
        if finished is not None:
            if finished:
                filter_dict["$expr"] = {
                    "$and": [
                        {"$gt": ["$total_duration", 0]},
                        {"$gte": [{"$divide": ["$last_position", "$total_duration"]}, 0.99]},
                    ]
                }
            else:
                filter_dict["$or"] = [
                    {"$expr": {"$lte": ["$total_duration", 0]}},
                    {"$expr": {"$lt": [{"$divide": ["$last_position", "$total_duration"]}, 0.99]}},
                ]
        if min_watch_times is not None:
            filter_dict["watch_count"] = {"$gte": min_watch_times}
        if max_watch_times is not None:
            filter_dict["watch_count"] = {"$lte": max_watch_times}
        if last_watched_after:
            filter_dict["last_watched"] = {"$gte": last_watched_after}

        sort = [("last_watched", -1)]

        skip = max(page - 1, 0) * size
        result = await self.repo.find(
            filter_dict, skip, size, sort, session=session
        )
        total = await self.repo.count(filter_query=filter_dict, session=session)
        pages = (total + size - 1) // size if total > 0 else 0

        return WatchHistoryPageResult(
            items=[self.read_model(**item.model_dump()) for item in result],
            total=total,
            page=page,
            size=size,
            pages=pages,
        )

    @logic_handler("按条件删除观看历史")
    async def delete_by_filter(
        self,
        user_id: Optional[str] = None,
        movie_ids: Optional[List[str]] = None,
        asset_ids: Optional[List[str]] = None,
        watch_type: Optional[WatchType] = None,
        session=None,
    ) -> int:
        filter_dict = {}
        if user_id:
            filter_dict["user_id"] = ObjectId(user_id)
        if movie_ids:
            if len(movie_ids) == 1:
                filter_dict["movie_id"] = ObjectId(movie_ids[0])
            else:
                filter_dict["movie_id"] = {"$in": [ObjectId(mid) for mid in movie_ids]}
        if asset_ids:
            if len(asset_ids) == 1:
                filter_dict["asset_id"] = ObjectId(asset_ids[0])
            else:
                filter_dict["asset_id"] = {"$in": [ObjectId(aid) for aid in asset_ids]}
        if watch_type:
            filter_dict["type"] = watch_type.value

        if not filter_dict:
            return 0

        # Hard Delete
        result = await self.repo.delete_many(filter_dict, soft_delete=False, session=session)
        
        if user_id:
             await self.cache_repo._delete_recent_list(user_id)
        
        return result

    # -------------------------- 播放记录：按资产查询/创建 -----------------------------
    @logic_handler("按用户+资产获取观看历史")
    async def get_by_asset(self, user_id: str, asset_id: str, asset_type: WatchType, session=None) -> Optional[WatchHistoryRead]:
        results = await self.repo.find(
            {"user_id": ObjectId(user_id), "asset_id": ObjectId(asset_id), "type": asset_type.value},
            skip=0,
            limit=1,
            sort=None,
            session=session,
        )
        if not results:
            return None
        return self.read_model(**results[0].model_dump())

    # -------------------------- 统计信息 -----------------------------
    @logic_handler("获取用户观看统计信息")
    async def get_watch_statistics(self, user_id: str, session=None) -> Dict[str, Any]:
        # 迁移自 Repo：聚合统计
        pipeline = [
            {"$match": {"user_id": ObjectId(user_id), "is_deleted": False}},
            {
                "$group": {
                    "_id": None,
                    "total_movies": {"$sum": 1},
                    "total_watch_time": {"$sum": "$total_watch_time"},
                    "total_watch_count": {"$sum": "$watch_count"},
                    "avg_progress": {
                        "$avg": {
                            "$cond": [
                                {"$gt": ["$total_duration", 0]},
                                {
                                    "$multiply": [
                                        {"$divide": ["$last_position", "$total_duration"]},
                                        100,
                                    ]
                                },
                                0,
                            ]
                        }
                    },
                }
            },
        ]
        result = await self.repo.aggregate(pipeline, session=session)
        if result:
            stats = result[0]
            return {
                "total_movies": stats.get("total_movies", 0),
                "total_watch_time": stats.get("total_watch_time", 0),
                "total_watch_count": stats.get("total_watch_count", 0),
                "avg_progress": round(stats.get("avg_progress", 0.0), 2),
            }
        else:
            return {
                "total_movies": 0,
                "total_watch_time": 0,
                "total_watch_count": 0,
                "avg_progress": 0.0,
            }

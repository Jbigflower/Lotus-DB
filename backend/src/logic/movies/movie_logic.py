# 顶部导入区（更新）
import json
from bson import ObjectId
from typing import Optional, List, Dict, Any

from src.logic.base_logic import BaseLogic
from src.repos import MovieRepo, MovieRedisRepo
from src.models import MovieCreate, MovieUpdate, MovieRead, MoviePageResult, MovieInDB
from src.core.exceptions import NotFoundError, ConflictError
from src.core.handler import logic_handler
from config.logging import get_logic_logger
from pymongo import UpdateOne


class MovieLogic(BaseLogic[MovieInDB, MovieCreate, MovieUpdate, MovieRead]):
    """
    电影逻辑层
    批处理 + 单例 混合使用
    """

    def __init__(self):
        super().__init__(
            repo=MovieRepo(),
            read_model=MovieRead,
            cache_repo=MovieRedisRepo(),
        )
        # 保持原有逻辑层 logger 命名
        self.logger = get_logic_logger("movie_logic")

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
    @logic_handler("获取电影详情")
    async def get_movie(self, movie_id: str, session=None) -> Optional[MovieRead]:
        return await super().get_by_id(movie_id, session=session)
    
    @logic_handler("获取多个电影详情")
    async def get_movies(self, movie_ids: List[str], session=None) -> List[MovieRead]:
        return await super().get_by_ids(movie_ids, session=session)

    @logic_handler("创建电影")
    async def create_movie(self, data: MovieCreate, session=None) -> MovieRead:
        exists = await self.repo.exists(
            {
                "title": data.title,
                "release_date": data.release_date.isoformat() if data.release_date else None,
                "library_id": ObjectId(data.library_id),
            },
            session=session,
        )
        if exists:
            raise ConflictError("电影已存在")
        return await super().create(data, session=session)

    @logic_handler("批量导入电影")
    async def create_batch(self, movies_data: List[MovieCreate], session=None):
        keys = {
            (
                m.title,
                m.release_date.isoformat() if m.release_date else None,
                m.library_id,
            )
            for m in movies_data
        }
        query = {
            "$or": [
                {
                    "title": t,
                    "release_date": r,
                    "library_id": ObjectId(l),
                }
                for (t, r, l) in keys
            ]
        }
        existing_docs = await self.repo.find(
            query,
            projection={"title": 1, "release_date": 1, "library_id": 1},
            session=session,
        )
        existing_keys = {
            (d["title"], d["release_date"], d["library_id"])
            for d in existing_docs
        }

        new_movies = [
            m
            for m in movies_data
            if (
                m.title,
                m.release_date.isoformat() if m.release_date else None,
                m.library_id,
            )
            not in existing_keys
        ]
        duplicates = [
            m
            for m in movies_data
            if (
                m.title,
                m.release_date.isoformat() if m.release_date else None,
                m.library_id,
            )
            in existing_keys
        ]

        return await super().create_batch(new_movies, session=session)

    @logic_handler("更新多个电影")
    async def update_movies(self, movie_ids: List[str], data: Dict[str, Any], session=None) -> List[MovieRead]:
        return await super().update_by_ids(movie_ids, data, session=session)

    @logic_handler("删除多个电影")
    async def delete_movies(self, movie_ids: List[str], soft_delete: bool = True, session=None) -> None:
        await super().deleted_by_ids(movie_ids, soft_delete=soft_delete, session=session)
    
    @logic_handler("恢复多个电影")
    async def restore_movies(self, movie_ids: List[str], session=None) -> None:
        await super().restore_by_ids(movie_ids, session=session)

    # ----------------------------- 子类特有方法 -----------------------------
    # -----------------------------  存在性检查  -----------------------------
    @logic_handler("快速检查电影是否全部存在")
    async def check_movie_exist_fast(self, movie_ids: List[str], session=None) -> bool:
        """快速检查：仅返回是否全部存在"""
        if not movie_ids:
            return True
        object_mids = [ObjectId(mid) for mid in movie_ids]
        count = await self.repo.count({"_id": {"$in": object_mids}}, session=session)
        return count == len(movie_ids)

    @logic_handler("细粒度检查电影是否存在")
    async def check_movie_exist_detail(self, movie_ids: List[str], session=None) -> Dict[str, bool]:
        """细粒度检查：返回每个电影ID是否存在"""
        if not movie_ids:
            return {}
        object_mids = [ObjectId(mid) for mid in movie_ids]
        existing_movies = await self.repo.find(
            {"_id": {"$in": object_mids}},
            projection={"_id": 1},
            session=session,
        )
        existing_ids = {str(m["_id"]) for m in existing_movies}
        return {mid: mid in existing_ids for mid in movie_ids}

    # -----------------------------  协同方法： Library  -----------------------------
    @logic_handler("列举所有的电影ID")
    async def list_library_movie_ids(self, library_id: str, session=None) -> List[str]:
        filter_dict: Dict[str, Any] = {}
        filter_dict["library_id"] = ObjectId(library_id)

        total_count = await self.repo.count(filter_dict, session=session)
        if total_count == 0:
            return []

        batch_size = self.repo.MAX_FIND_LIMIT
        results: List[Dict[str, Any]] = []
        last_id: Optional[str] = None

        while len(results) < total_count:
            query = dict(filter_dict)
            if last_id:
                query["_id"] = {"$gt": ObjectId(last_id)}
            batch = await self.repo.find(
                filter_dict=query,
                limit=batch_size,
                sort=[("_id", 1)],
                projection={"_id": 1},
                session=session,
            )
            if not batch:
                break
            results.extend(batch)
            last_id = str(batch[-1]["_id"]) if batch else None

        return [str(doc["_id"]) for doc in results]

    # -------------------------- 特殊更新 -----------------------------
    @logic_handler("批量更新电影的封面、海报情况")
    async def update_movie_artworks(self, movie_ids: List[str], data: Dict[str, Any], session=None) -> None:
        """
        :param movie_ids: 电影ID列表
        :param data: 包含每个电影ID的更新数据字典
        :param session: 数据库会话
        """
        if not movie_ids:
            return
        updates = []
        for mid in movie_ids:
            updates.append(
                UpdateOne(
                    {"_id": ObjectId(mid)},
                    {"$set": data[mid]}
                )
            )
        if updates:
            await self.repo.collection.bulk_write(updates, ordered=False, session=session)
        # 刷新缓存
        await self.cache_repo.delete_details_batch(movie_ids)

    # -------------------------- search Bar -----------------------------
    @logic_handler("综合搜索电影")
    async def list_movies(
        self,
        query: Optional[str],
        genres: Optional[List[str]],
        min_rating: Optional[float],
        max_rating: Optional[float],
        start_date: Optional[str],
        end_date: Optional[str],
        tags: Optional[List[str]],
        is_deleted: Optional[bool],
        page: int,
        size: int,
        sort: Optional[List[Dict[str, Any]]] = None,
        addition_filter: Optional[Dict[str, Any]] = None,
        library_id: Optional[str] = None,
        library_ids: Optional[List[str]] = None,
        session=None,
    ) -> MoviePageResult:
        params = {k: v for k, v in locals().items() if k not in ("self", "session")}
        search_key = self._build_search_key(**params)
        # 直接调用 DualLayerCache 的搜索页缓存能力
        cached = await self.cache_repo.get_search_page(search_key, page)
        if cached:
            items = [MovieRead(**item) for item in cached.get("items", [])]
            return MoviePageResult(
                total=cached.get("total", len(items)),
                page=cached.get("page", page),
                size=cached.get("size", len(items)),
                items=items,
            )

        filter_dict: Dict[str, Any] = {}
        and_conditions: List[Dict[str, Any]] = []

        if query:
            text_fields = ["title", "title_cn", "description", "description_cn", "directors", "actors"]
            and_conditions.append({"$or": [{f: {"$regex": query, "$options": "i"}} for f in text_fields]})
        
        if genres:
            filter_dict["genres"] = {"$in": genres}
        if min_rating is not None or max_rating is not None:
            rating_cond: Dict[str, Any] = {}
            if min_rating is not None:
                rating_cond["$gte"] = min_rating
            if max_rating is not None:
                rating_cond["$lte"] = max_rating
            filter_dict["rating"] = rating_cond
        if start_date or end_date:
            date_cond: Dict[str, Any] = {}
            if start_date:
                date_cond["$gte"] = start_date
            if end_date:
                date_cond["$lte"] = end_date
            filter_dict["release_date"] = date_cond
        if tags:
            filter_dict["tags"] = {"$in": tags}
        if library_id:
            filter_dict["library_id"] = ObjectId(library_id)
        if library_ids:
            filter_dict["library_id"] = {"$in": [ObjectId(lid) for lid in library_ids]}
        if is_deleted is not None:
            filter_dict["is_deleted"] = is_deleted
        
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

        skip = max(page - 1, 0) * size
        results = await self.repo.find(
            filter_dict,
            skip=skip,
            limit=size,
            sort=sort,
            session=session,
        )
        total = await self.repo.count(filter_dict, session=session)
        pages = (total + size - 1) // size

        page_result = MoviePageResult(items=results, total=total, page=page, size=size, pages=pages)
        # 统一使用 DualLayerCache 的搜索页缓存
        await self.cache_repo.cache_search_page(search_key, page, page_result.model_dump())
        return page_result

    @logic_handler("获取最近添加的电影")
    async def list_recent_movies(
        self,
        library_ids: Optional[List[str]] = None,
        size: int = 20,
        session=None,
    ) -> List[MovieRead]:
        #TODO 缓存添加
        filter_dict: Dict[str, Any] = {"is_deleted": False}
        if library_ids:
            filter_dict["library_id"] = {"$in": [ObjectId(lid) for lid in library_ids]}

        results = await self.repo.find(
            filter_dict,
            limit=size,
            sort=[("created_at", -1)],
            session=session,
        )
        return [MovieRead(**doc.model_dump()) for doc in results]

    # -------------------------- 统计信息 -----------------------------
    @logic_handler("获取电影统计信息")
    async def get_movie_stats(self, movie_id: str, session=None) -> dict:
        """获取电影的统计信息，包含了电影资产个数"""
        return {}
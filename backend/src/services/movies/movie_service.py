# 顶部导入替换为文件操作逻辑类
import os
import json
from typing import List, Dict, Any, Optional, Union
from config.logging import get_service_logger
from src.core.handler import service_handler
from src.core.exceptions import NotFoundError, BadRequestError, ForbiddenError
from src.logic import TaskLogic, MovieLogic, LibraryLogic, WatchHistoryLogic
from src.logic.file.film_asset_file_ops import FilmAssetFileOps
from src.models import (
    MovieCreate,
    TaskCreate,
    TaskStatus,
    MovieUpdate,
    MoviePageResult,
    MovieRead,
    MovieReadWithFlags,
    TaskType,
    TaskSubType,
    TaskRead
)
from src.logic import CollectionLogic
from src.models import CustomListType
from src.async_worker.core import send_task, TaskPriority
from src.models import UserRole

class MovieService:
    def __init__(self):
        self.logic = MovieLogic()
        self.task_logic = TaskLogic()
        self.library_logic = LibraryLogic()
        self.file_logic = FilmAssetFileOps()
        self.collection_logic = CollectionLogic()
        self.logger = get_service_logger("movie_service")

    async def _ensure_user_read_permission(self, current_library, current_user) -> None:
        """检查用户是否有读取库的权限"""
        if current_library.is_public:
            return
        if current_user.role == UserRole.ADMIN:
            return
        if current_user.id == current_library.user_id:
            return
        raise ForbiddenError("当前用户权限不可触发读操作")

    async def _ensure_user_edit_permission(self, current_library, current_user) -> None:
        """检查用户是否有操作库的权限"""
        if current_user.role == UserRole.GUEST:
            raise ForbiddenError("访客不可触发写操作")
        if current_user.role == UserRole.ADMIN:
            return
        if current_user.id == current_library.user_id:
            return
        raise ForbiddenError("当前用户权限不可触发写操作")

    @service_handler(action="list_movies")
    async def list_movies(
        self,
        *,
        query: Optional[str] = None,
        genres: Optional[List[str]] = None,
        min_rating: Optional[float] = None,
        max_rating: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_deleted: Optional[bool] = None,
        page: int = 1,
        size: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: Optional[int] = None,
        current_user=None,
        library_id: Optional[str] = None,
    ) -> MoviePageResult:
        target_library_ids = None
        
        if library_id:
            current_library = await self.library_logic.get_library(library_id)
            await self._ensure_user_read_permission(current_library, current_user)
        else:
            # 只有管理员可以查看所有库的电影，普通用户只能查看自己有权限的库
            if current_user.role != UserRole.ADMIN:
                # 获取用户可访问的所有库（包括自己的和公开的）
                libraries_page = await self.library_logic.list_libraries(
                    role=current_user.role,
                    user_id=current_user.id,
                    only_me=False,
                    page=1,
                    page_size=1000  # 假设用户库数量不会太多
                )
                if not libraries_page.items:
                    return MoviePageResult(
                        items=[], total=0, page=page, size=size, pages=0
                    )
                target_library_ids = [lib.id for lib in libraries_page.items]

        sort = [(sort_by, sort_dir)] if sort_by and sort_dir else None
        page_result = await self.logic.list_movies(
            query=query,
            genres=genres,
            min_rating=min_rating,
            max_rating=max_rating,
            start_date=start_date,
            end_date=end_date,
            tags=tags,
            library_id=library_id,
            library_ids=target_library_ids,
            page=page,
            size=size,
            sort=sort,
            is_deleted=is_deleted,
        )
        items = await self._inject_user_flags(page_result.items, current_user=current_user)
        return MoviePageResult(
            items=items,
            total=page_result.total,
            page=page_result.page,
            size=page_result.size,
            pages=page_result.pages,
        )

    @service_handler(action="list_recent_movies")
    async def list_recent_movies(
        self,
        *,
        library_id: Optional[str] = None,
        size: int = 20,
        current_user=None,
    ) -> List[MovieReadWithFlags]:
        if library_id:
            # 指定库：校验读取权限后查询
            current_library = await self.library_logic.get_library(library_id)
            await self._ensure_user_read_permission(current_library, current_user)
            movies = await self.logic.list_recent_movies([library_id], size=size)
            return await self._inject_user_flags(movies, current_user=current_user)

        # 未指定库：获取当前用户可访问的所有库，再汇总查询
        libraries_page = await self.library_logic.list_libraries(
            role=current_user.role,
            user_id=getattr(current_user, "id", None),
            only_me=False,
            page=1,
            page_size=500,
        )
        library_ids = [lib.id for lib in libraries_page.items] if libraries_page.items else []
        if not library_ids:
            return []
        movies = await self.logic.list_recent_movies(library_ids, size=size)
        return await self._inject_user_flags(movies, current_user=current_user)

    @service_handler(action="list_recycle_bin_movies")
    async def list_recycle_bin_movies(
        self,
        *,
        page: int = 1,
        size: int = 20,
        current_user=None,
    ) -> MoviePageResult:
        # 获取用户可访问/管理的库
        # 对于回收站，只展示用户有权限管理的库中的已删除项
        only_me = True
        if current_user.role == UserRole.ADMIN:
            only_me = False
            
        libraries_page = await self.library_logic.list_libraries(
            role=current_user.role,
            user_id=current_user.id,
            only_me=only_me,
            page=1,
            page_size=1000,
        )
        library_ids = [lib.id for lib in libraries_page.items] if libraries_page.items else []
        
        if not library_ids:
            return MoviePageResult(
                items=[],
                total=0,
                page=page,
                size=size,
                pages=0,
            )

        page_result = await self.logic.list_movies(
            query=None,
            genres=None,
            min_rating=None,
            max_rating=None,
            start_date=None,
            end_date=None,
            tags=None,
            is_deleted=True,
            library_id=None,
            library_ids=library_ids,
            page=page,
            size=size,
        )
        
        items = await self._inject_user_flags(page_result.items, current_user=current_user)
        return MoviePageResult(
            items=items,
            total=page_result.total,
            page=page_result.page,
            size=page_result.size,
            pages=page_result.pages,
        )

    @service_handler(action="get_movie_detail")
    async def get_movie(
        self, movie_id: str, *, current_user=None
    ) -> MovieReadWithFlags:
        movie = await self.logic.get_movie(movie_id)
        target_library = await self.library_logic.get_library(movie.library_id)
        await self._ensure_user_read_permission(target_library, current_user)
        injected = await self._inject_user_flags([movie], current_user=current_user)
        return injected[0]

    async def _inject_user_flags(
        self,
        movies: List[MovieRead],
        *,
        current_user,
    ) -> List[MovieReadWithFlags]:
        if not current_user or not getattr(current_user, "id", None):
            return [MovieReadWithFlags(**m.model_dump()) for m in movies]
        user_collections = await self.collection_logic.get_user_collections(current_user.id)
        fav_ids, watch_ids = [], []
        for c in user_collections:
            if c.type == CustomListType.FAVORITE:
                fav_ids = c.movies 
            if c.type == CustomListType.WATCHLIST:
                watch_ids = c.movies 
        decorated: List[MovieReadWithFlags] = []
        for m in movies:
            decorated.append(
                MovieReadWithFlags(
                    **m.model_dump(),
                    is_favoriter=m.id in fav_ids,
                    is_watchLater=m.id in watch_ids,
                )
            )
        return decorated

    # -------------------------- Nginx 签名（电影图片-批量） -----------------------------
    @service_handler(action="list_movie_covers_signed")
    async def list_movie_covers_signed(
        self,
        ids: List[str],
        kind: str,
        *,
        current_user=None,
    ) -> List[str]:
        """
        批量生成影片图片（poster/thumbnail/backdrop）的签名 URL，仅返回存在的类型。
        当 kind='all' 时，顺序：poster → thumbnail → backdrop。
        """
        valid = {"poster.jpg", "thumbnail.jpg", "backdrop.jpg", "all"}
        if kind not in valid:
            raise BadRequestError("图片类型非法：仅支持 poster.jpg | thumbnail.jpg | backdrop.jpg | all")

        # 批量拉取影片，基于存在性字段过滤
        movies = await self.logic.get_movies(ids)

        library_ids = set([m.library_id for m in movies if m.library_id])
        for lib_id in library_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_read_permission(lib, current_user)

        file_order = (
            ["poster.jpg", "thumbnail.jpg", "backdrop.jpg"] if kind == "all" else [kind]
        )
        flag_map = {
            "poster.jpg": "has_poster",
            "thumbnail.jpg": "has_thumbnail",
            "backdrop.jpg": "has_backdrop",
        }
        self.logger.info(movies)
        signed: List[str] = []
        for m in movies:
            for fname in file_order:
                if getattr(m, flag_map[fname], False):
                    lib_id = m.library_id
                    url, _ = self.file_logic.build_library_signed_url(lib_id, f"{m.id}/{fname}")
                    self.logger.info(f"生成签名 URL 成功：{url}")
                    signed.append(url)
        return signed

    @service_handler(action="create_movie")
    async def create_movie(
        self, data: MovieCreate, *, current_user=None
    ) -> Union[MovieRead, str]:
        payload = data.model_dump(exclude_unset=True)
        lib_id = payload.get("library_id")
        if not lib_id:
            raise BadRequestError("library_id 不能为空")
        current_library = await self.library_logic.get_library(lib_id)
        await self._ensure_user_edit_permission(current_library, current_user)
        created = await self.logic.create_movie(MovieCreate(**payload))

        parameters = {
            "title": created.title,
            "movie_id": created.id,
            "library_id": current_library.id,
            "plugin_names": current_library.activated_plugins.get('metadata', []),
            "release_date": created.release_date.isoformat() if created.release_date else None,
        }

        task = await self.task_logic.create_task(
            TaskCreate(
                name="下载电影文件",
                description=f"下载 {created.title} 的文件",
                task_type=TaskType.DOWNLOAD,
                sub_type=TaskSubType.DOWNLOAD_MOVIE_FILE,
                status=TaskStatus.PENDING,
                parameters=parameters,
                user_id=current_user.id if current_user else None,
            )
        )
        await send_task(
            "download_movie_thumb_task",
            parameters,
            TaskPriority.HIGH,
        )
        return created, task.id

    @service_handler(action="replace_movie_poster")
    async def replace_movie_poster(
        self,
        movie_id: str,
        file,
        *,
        current_user=None,
    ) -> MovieRead:
        movie = await self.logic.get_movie(movie_id)
        current_library = await self.library_logic.get_library(movie.library_id)
        await self._ensure_user_edit_permission(current_library, current_user)
        if not file:
            raise BadRequestError("文件不能为空")
        _ = self.file_logic.save_movie_poster(file, current_library.id, movie_id)
        # 标记 has_poster
        await self.logic.update_movie_artworks([movie_id], {movie_id: {"has_poster": True}})
        return await self.get_movie(movie_id, current_user=current_user)

    @service_handler(action="replace_movie_images")
    async def replace_movie_images(
        self,
        movie_id: str,
        files,
        types,
        *,
        current_user=None,
    ) -> MovieRead:
        movie = await self.logic.get_movie(movie_id)
        current_library = await self.library_logic.get_library(movie.library_id)
        await self._ensure_user_edit_permission(current_library, current_user)
        if not files or not types or len(files) != len(types):
            raise BadRequestError("文件与类型数量不匹配")
        flags: Dict[str, bool] = {}
        for i, t in enumerate(types):
            f = files[i]
            if t == "poster":
                self.file_logic.save_movie_poster(f, current_library.id, movie_id)
                flags["has_poster"] = True
            elif t == "backdrop":
                self.file_logic.save_movie_backdrop(f, current_library.id, movie_id)
                flags["has_backdrop"] = True
            else:
                raise BadRequestError("图片类型仅支持 poster/backdrop")
        if flags:
            await self.logic.update_movie_artworks([movie_id], {movie_id: flags})
        return await self.get_movie(movie_id, current_user=current_user)

    @service_handler(action="scrape_movie_metadata")
    async def scrape_movie_metadata(
        self,
        movie_id: str,
        plugin_names: Optional[List[str]] = None,
        *,
        current_user=None,
    ) -> tuple[TaskRead, dict]:
        movie = await self.logic.get_movie(movie_id)
        current_library = await self.library_logic.get_library(movie.library_id)
        await self._ensure_user_edit_permission(current_library, current_user)
        plugins = plugin_names or current_library.activated_plugins.get('metadata', [])
        if not plugins:
            raise BadRequestError("当前库未激活元数据插件")
        parameters = {
            "movie_id": movie_id,
            "plugin_names": plugins,
        }
        task = await self.task_logic.create_task(
            TaskCreate(
                name="提取电影元数据",
                description=f"提取 {movie_id} 的元数据",
                task_type=TaskType.ANALYSIS,
                sub_type=TaskSubType.EXTRACT_METADATA,
                status=TaskStatus.PENDING,
                parameters=parameters,
                user_id=current_user.id if current_user else None,
            )
        )
        await send_task(
            "extract_metadata",
            parameters,
            TaskPriority.NORMAL,
        )
        return task, {"task_id": task.id}

    @service_handler(action="scrape_movie_subtitles")
    async def scrape_movie_subtitles(
        self,
        movie_id: str,
        plugin_names: Optional[List[str]] = None,
        *,
        current_user=None,
    ) -> tuple[TaskRead, dict]:
        movie = await self.logic.get_movie(movie_id)
        current_library = await self.library_logic.get_library(movie.library_id)
        await self._ensure_user_edit_permission(current_library, current_user)
        plugins = plugin_names or current_library.activated_plugins.get('metadata', [])
        if not plugins:
            raise BadRequestError("当前库未激活字幕插件")
        parameters = {
            "movie_id": movie_id,
            "plugin_names": plugins,
        }
        task = await self.task_logic.create_task(
            TaskCreate(
                name="下载电影字幕",
                description=f"下载 {movie_id} 的字幕",
                task_type=TaskType.DOWNLOAD,
                sub_type=TaskSubType.DOWNLOAD_SUBTITLE_FILE,
                status=TaskStatus.PENDING,
                parameters=parameters,
                user_id=current_user.id if current_user else None,
            )
        )
        await send_task(
            "download_subtitle_task",
            parameters,
            TaskPriority.NORMAL,
        )
        return task, {"task_id": task.id}

    @service_handler(action="import_movies_batch")
    async def import_movies_from_file(
        self, file, *, current_user=None, library_id: str = None
    ) -> tuple[TaskRead, dict]:
        try:
            content = await file.read()
            movies_data = json.loads(content)
        except json.JSONDecodeError:
            raise BadRequestError("JSON 格式错误")
        if not movies_data or not isinstance(movies_data, list):
            raise BadRequestError("电影数据格式错误")

        current_library = await self.library_logic.get_library(library_id)
        await self._ensure_user_edit_permission(current_library, current_user)
        for movie in movies_data:
            movie["library_id"] = library_id

        task = await self.task_logic.create_task(
            TaskCreate(
                name="导入电影",
                description=f"导入 {len(movies_data)} 条电影数据",
                task_type=TaskType.IMPORT,
                sub_type=TaskSubType.MOVIE_IMPORT,
                status=TaskStatus.PENDING,
                user_id=current_user.id if current_user else None,
            )
        )
        await send_task(
            "import_movies",
            {
                "movies_data": movies_data,
                "task_id": task.id,
                "library": {
                    "id": current_library.id,
                    "path": current_library.root_path,
                    "activated_plugins": current_library.activated_plugins,
                },
            },
            TaskPriority.HIGH,
        )
        return task, {"task_id": task.id, "desc": f"导入 {len(movies_data)} 条电影数据"}

    @service_handler(action="update_movies_by_ids")
    async def update_movies_by_ids(
        self,
        movie_ids: List[str],
        patch: MovieUpdate,
        *,
        current_user=None,
    ) -> List[MovieRead]:
        if len(movie_ids) == 0:
            raise BadRequestError("电影ID列表不能为空")
        movies = await self.logic.get_movies(movie_ids)
        lib_ids = set(m.library_id for m in movies)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_edit_permission(lib, current_user)
        patch_dict = patch.model_dump(exclude_unset=True)
        movies = await self.logic.update_movies(movie_ids, patch_dict)
        return movies

    @service_handler(action="delete_movies_by_ids")
    async def delete_movies_by_ids(
        self,
        movie_ids: List[str],
        *,
        current_user=None,
        soft_delete: bool = True,
    ) -> Dict[str, Any]:
        if len(movie_ids) == 0:
            raise BadRequestError("电影ID列表不能为空")
        movies = await self.logic.get_movies(movie_ids)
        lib_ids = set(m.library_id for m in movies)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_edit_permission(lib, current_user)

        if soft_delete:
            count = await self.logic.delete_movies(movie_ids, soft_delete=True)
            success = count if isinstance(count, int) else len(movie_ids)
            failed = len(movie_ids) - success
            return {"message": "软删除完成", "success": success, "failed": failed}
        else:
            from src.logic import MovieAssetLogic
            asset_logic = MovieAssetLogic()
            watch_history_logic = WatchHistoryLogic()
            
            async with self.logic.repo.transaction() as session:
                _asset_deleted = await asset_logic.delete_movies_assets(
                    movie_ids, soft_delete=False, session=session
                )
                
                # 同步删除播放记录
                await watch_history_logic.delete_by_filter(movie_ids=movie_ids, session=session)
                
                await self.logic.delete_movies(
                    movie_ids, soft_delete=False, session=session
                )

            for m in movies:
                self.file_logic.delete_dir(os.path.join(m.library_id, m.id))
            return {"message": "硬删除完成", "success": len(movie_ids), "failed": 0}

    @service_handler(action="重建多个电影")
    async def restore_movies_by_ids(
        self,
        movie_ids: List[str],
        *,
        current_user=None,
    ) -> List[MovieRead]: 
        if len(movie_ids) == 0:
            raise BadRequestError("电影ID列表不能为空")
        movies = await self.logic.get_movies(movie_ids)
        lib_ids = set(m.library_id for m in movies)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_edit_permission(lib, current_user)
        movies = await self.logic.restore_by_ids(movie_ids)
        return movies

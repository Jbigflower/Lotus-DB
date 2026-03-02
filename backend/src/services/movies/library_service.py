from typing import Optional, List, Dict, Any, Tuple, Set, Callable
from fastapi import UploadFile
from src.models import TaskCreate, TaskType, TaskSubType, TaskStatus, TaskPriority, UserRead, UserRole
from src.logic import TaskLogic, LibraryLogic, UserLogic, WatchHistoryLogic
from src.logic.file.film_asset_file_ops import FilmAssetFileOps
from src.core.exceptions import (
    NotFoundError,
    ConflictError,
    ValidationError,
    BadRequestError,
    ForbiddenError,
)
from src.models import (
    LibraryCreate,
    LibraryRead,
    LibraryUpdate,
    LibraryType,
    LibraryPageResult,
)

from src.async_worker.core import send_task
from src.core.handler import service_handler
from config.logging import get_service_logger


class LibraryService:
    """
    库服务：
    - 提供库的创建、查询、更新、删除等操作
    - 委托 MovieLogic 处理业务逻辑
    - 处理数据库操作异常，转换为 HTTPException
    - 记录操作日志
    """

    def __init__(self):
        self.logic = LibraryLogic()
        self.user_logic = UserLogic()
        self.task_logic = TaskLogic()
        self.file_logic = FilmAssetFileOps()
        self.logger = get_service_logger("library_service")

    async def _ensure_user_read_permission(
        self,
        library_id: str,
        *,
        current_user,
    ) -> None:
        """检查用户是否有操作库的权限"""
        library = await self.logic.get_library(library_id)
        if current_user.role == UserRole.ADMIN:
            return
        else:
            if (
                library.user_id != current_user.id
                and not library.is_public
            ):
                raise ForbiddenError("无权限")

    async def _ensure_user_edit_permission(
        self,
        library_id: str,
        *,
        current_user,
    ) -> None:
        """检查用户是否有操作库的权限"""
        if current_user.role == UserRole.GUEST:
            raise ForbiddenError("访客不可触发操作")
        else:
            library = await self.logic.get_library(library_id)
            if (
                library.user_id != current_user.id
                and current_user.role == UserRole.USER
            ):
                raise ForbiddenError("无权限")

    # ----------------------------- CRUD -----------------------------
    @service_handler(action="get_library")
    async def get_library(self, library_id: str, current_user) -> LibraryRead:
        library = await self.logic.get_library(library_id)
        await self._ensure_user_read_permission(library_id, current_user=current_user)
        return library

    @service_handler(action="create_library")
    async def create_library(
        self, library_create: LibraryCreate, current_user
    ) -> LibraryRead:
        """创建库（服务层仅接收 Model 层模型）"""
        if current_user.role == UserRole.GUEST:
            raise ForbiddenError("访客不可创建库")

        # 路由层已负责转换与填充默认值，这里做稳健性补全
        payload = library_create.model_dump()
        payload.setdefault("user_id", current_user.id)
        payload.setdefault("root_path", "temp")
        data = LibraryCreate(**payload)

        # 创建库
        library = await self.logic.create_library(data)

        # 确保库根路径可读写
        try:
            self.file_logic.make_dir_rw(self.file_logic._resolve_library_root(library.id))
        except Exception as e:
            await self.logic.delete_library(library.id, soft_delete=False)
            raise ValidationError(f"创建库根路径失败: {e}")

        # 更新库根路径为库ID
        library = await self.logic.update_library_root_path(library.id, library.id)
        return library

    @service_handler(action="update_library")
    async def update_library(
        self, library_id: str, library_update: LibraryUpdate, current_user
    ) -> LibraryRead:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        # 路由层已做 exclude_unset 转换，这里直接传递
        return await self.logic.update_library(library_id, library_update)

    @service_handler(action="delete_library")
    async def delete_library(
        self, library_id: str, *, current_user, soft_delete: bool = True
    ) -> Tuple[LibraryRead, Optional[Dict[str, str]]]:
        """
        删除库（服务层返回 Model 层模型；若触发后台任务，附带 task-id 字典）
        - 软删除：返回删除后的库模型（is_deleted=True），不附带任务
        - 硬删除：返回删除前的库模型（用于上下文描述），附带任务字典 {task_id: 描述}
        """
        await self._ensure_user_edit_permission(library_id, current_user=current_user)

        # 先获取库详情用于校验、日志与后续清理任务（作为 Model 返回的一部分）
        library = await self.logic.get_library(library_id)

        # 移除与“当前库”状态的耦合，不再阻止删除

        task_ctx: Optional[Dict[str, str]] = None

        # 硬删除 ｜ 物理删除
        if not soft_delete:
            from src.logic import MovieLogic, MovieAssetLogic

            movie_logic = MovieLogic()
            assets_logic = MovieAssetLogic()
            watch_history_logic = WatchHistoryLogic()

            # 事务删除 库资产 ｜ 电影 ｜ 库
            async with self.logic.repo.transaction() as session:
                movie_ids = await movie_logic.list_library_movie_ids(library_id, session=session)
                assets_count = await assets_logic.delete_library_assets(
                    library_id, movie_ids, soft_delete=False, session=session
                )
                
                # 同步删除播放记录
                if movie_ids:
                    await watch_history_logic.delete_by_filter(movie_ids=movie_ids, session=session)

                _ = await movie_logic.delete_movies(
                    movie_ids, soft_delete=False, session=session
                )
                _ = await self.logic.delete_library(
                    library_id, soft_delete=False, session=session
                )
                self.logger.info(
                    f"删除库:{library.name}，删除资产数量:{assets_count}，删除电影数量:{len(movie_ids)}"
                )
            # 创建任务：清理库文件（使用删除前获取的库信息）
            task_info = await self.task_logic.create_task(
                TaskCreate(
                    name=f"清理库文件任务:{library.name}",
                    user_id=current_user.id,
                    description="删除库根目录及其所有文件，避免阻塞主事件循环",
                    task_type=TaskType.MAINTENANCE,
                    sub_type=TaskSubType.CLEANUP_LIBRARY_FILES,
                    priority=TaskPriority.HIGH,
                    parameters={
                        "library_id": library_id,
                        "root_path": library.root_path,
                    },
                )
            )
            # 后台删除开始：清理库文件
            await send_task(
                TaskSubType.CLEANUP_LIBRARY_FILES,
                {"root_path": library.root_path, "task_id": task_info.id},
                TaskPriority.HIGH,
            )
            # 返回删除前的库模型 + 任务上下文字典（id: 描述）
            task_ctx = {task_info.id: "清理库文件任务：删除库根目录及其所有文件"}
            return library, task_ctx

        # 软删除：返回删除后的库模型
        ok = await self.logic.delete_library(library_id, soft_delete=True)
        if not ok:
            raise NotFoundError("删除失败，库不存在或已删除")
        deleted_library = await self.logic.get_library(library_id)
        return deleted_library, None

    @service_handler(action="restore_library")
    async def restore_library(self, library_id: str, current_user) -> LibraryRead:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        return await self.logic.restore_library(library_id)

    # -------------------------- search Bar -----------------------------
    @service_handler(action="list_libraries")
    async def list_libraries(
        self,
        current_user: UserRead,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
        library_type: Optional[LibraryType] = None,
        is_active: Optional[bool] = None,
        is_deleted: Optional[bool] = None,
        auto_import: Optional[bool] = None,
        only_me: bool = False,
    ) -> LibraryPageResult:
        """
        查询库列表
        """
        page_result = await self.logic.list_libraries(
            role=current_user.role,
            user_id=current_user.id,
            only_me=only_me,
            query=query,
            library_type=library_type,
            is_active=is_active,
            is_deleted=is_deleted,
            auto_import=auto_import,
            page=page,
            page_size=page_size,
        )
        return page_result

    # -------------------------- 进入/退出/查询 当前库-------------------------
    @service_handler(action="enter_library")
    async def enter_library(self, library_id: str, *, current_user) -> LibraryRead:
        raise BadRequestError("接口已下线：无需进入库，显式传参即可")

    @service_handler(action="get_current_library")
    async def get_current_library(self, *, current_user) -> Optional[LibraryRead]:
        raise BadRequestError("接口已下线：请显式传递 library_id 或从资源派生")

    @service_handler(action="exit_library")
    async def exit_library(self, *, current_user) -> bool:
        raise BadRequestError("接口已下线：无需退出库，显式传参即可")

    # -------------------------- 特殊更新 -----------------------------
    @service_handler(action="set_library_activity")
    async def update_library_activity(
        self, library_id: str, is_active: bool, *, current_user
    ) -> LibraryRead:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        return await self.logic.update_library_activity(library_id, is_active)

    @service_handler(action="set_library_visibility")
    async def update_library_visibility(
        self, library_id: str, is_public: bool, *, current_user
    ) -> LibraryRead:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        return await self.logic.update_library_visibility(library_id, is_public)

    # -------------------------- 统计信息 -----------------------------
    @service_handler(action="get_library_stats")
    async def get_library_stats(self, library_id: str, *, current_user) -> Dict:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        return await self.logic.get_library_stats(library_id)

    # -------------------------- Nginx 签名（批量） -----------------------------
    @service_handler(action="list_library_covers_signed")
    async def list_library_covers_signed(self, ids: List[str], *, current_user) -> List[str]:
        signed_url_list = []
        for id in ids:
            await self._ensure_user_read_permission(id, current_user=current_user)
            url, _ = self.file_logic.build_library_signed_url(id, 'backdrop.jpg')
            signed_url_list.append(url)
        return signed_url_list

    # ---- 上传库封面（权限检查 + 文件保存） ---- #
    @service_handler(action="upload_library_cover")
    async def upload_library_cover(self, library_id: str, upload: UploadFile, *, current_user) -> bool:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        self.file_logic.save_library_cover(upload, library_id)
        return True

    # -------------------------- 后续拓展 -----------------------------
    @service_handler(action="scan_library")
    async def scan_library(self, library_id: str, *, current_user) -> dict:
        await self._ensure_user_edit_permission(library_id, current_user=current_user)
        return await self.logic.scan_library(library_id)
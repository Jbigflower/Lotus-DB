# 顶部导入替换为文件操作逻辑类
import os
import subprocess
from typing import Optional, Dict, Any, List
from starlette.responses import StreamingResponse
from src.logic import MovieAssetLogic, MovieLogic, LibraryLogic, WatchHistoryLogic
from src.models import AssetType, AssetUpdate, AssetRead, UserRole, AssetStoreType, AssetCreate, AssetPageResult
from src.logic.file.film_asset_file_ops import FilmAssetFileOps
from src.async_worker.core import send_task, TaskPriority
from src.core.exceptions import NotFoundError, ForbiddenError, BadRequestError
from src.core.handler import service_handler
from config.logging import get_service_logger

class MovieAssetService:
    def __init__(self):
        self.logic = MovieAssetLogic()
        self.movie_logic = MovieLogic()
        self.library_logic = LibraryLogic()
        self.file_logic = FilmAssetFileOps()
        self.logger = get_service_logger("asset_service")

    async def _ensure_user_read_permission(self, current_user, current_library) -> None:
        """检查用户是否有读取库的权限"""
        if not current_library:
            raise NotFoundError("库不存在")
        if current_library.is_public:
            return
        if current_user.role == UserRole.ADMIN:
            return
        if current_user.id == current_library.user_id:
            return
        raise ForbiddenError("当前用户权限不可触发读操作")

    async def _ensure_user_edit_permission(self, current_user, current_library) -> None:
        if not current_library:
            raise NotFoundError("库不存在")
        if current_user.role == UserRole.ADMIN:
            return
        if current_user.id == current_library.user_id:
            return
        raise ForbiddenError("当前用户权限不可触发写操作")

    @service_handler(action="get_asset")
    async def get_asset(
        self, asset_id: str, *, current_user
    ) -> AssetRead:
        asset = await self.logic.get_asset(asset_id)
        if not asset:
            raise NotFoundError("资产不存在")
        library = await self.library_logic.get_library(asset.library_id)
        await self._ensure_user_read_permission(current_user, library)
        return asset

    @service_handler(action="update_asset")
    async def update_asset(
        self,
        asset_id: str,
        patch: AssetUpdate,
        *,
        current_user,
    ) -> AssetRead:
        asset = await self.logic.get_asset(asset_id)
        library = await self.library_logic.get_library(asset.library_id)
        await self._ensure_user_edit_permission(current_user, library)
        updated = await self.logic.update_asset(asset_id, patch)
        return updated

    @service_handler(action="update_movie_asset")
    async def update_movie_asset(
        self,
        asset_id: str,
        patch: AssetUpdate,
        *,
        current_user,
    ) -> AssetRead:
        patch_dict = patch.model_dump(exclude_unset=True)
        asset = await self.logic.get_asset(asset_id)
        library = await self.library_logic.get_library(asset.library_id)
        await self._ensure_user_edit_permission(current_user, library)
        return await self.logic.update_asset(asset_id, patch_dict)

    @service_handler(action="delete_assets")
    async def delete_assets(
        self,
        asset_ids: List[str],
        *,
        current_user,
        soft_delete: bool = True,
    ) -> int:
        assets_for_check = await self.logic.get_assets(asset_ids)
        lib_ids = set(a.library_id for a in assets_for_check)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_edit_permission(current_user, lib)

        # 硬删除需要文件操作，先取详情
        assets: List[AssetRead] = []
        if not soft_delete:
            assets = await self.logic.get_assets(asset_ids)

        async with self.logic.repo.transaction() as session:
            count = await self.logic.delete_assets(
                asset_ids, soft_delete=soft_delete, session=session
            )

            # 同步删除播放记录
            if not soft_delete and count > 0:
                 watch_history_logic = WatchHistoryLogic()
                 await watch_history_logic.delete_by_filter(asset_ids=asset_ids, session=session)

        # 硬删除：本地文件清理
        if not soft_delete and count:
            for asset in assets:
                if asset.store_type == AssetStoreType.LOCAL and asset.actual_path:
                    self.file_logic.delete_file(os.path.join(asset.library_id, asset.actual_path))

        return count

    @service_handler(action="delete_movie_assets")
    async def delete_movie_assets(
        self,
        asset_ids: List[str],
        *,
        current_user,
        soft_delete: bool = True,
    ) -> int:
        assets_for_check = await self.logic.get_assets(asset_ids)
        lib_ids = set(a.library_id for a in assets_for_check)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_edit_permission(current_user, lib)

        # 硬删除需要文件操作，先取详情
        assets: List[AssetRead] = []
        if not soft_delete:
            assets = await self.logic.get_assets(asset_ids)

        async with self.logic.repo.transaction() as session:
            count = await self.logic.delete_assets(
                asset_ids, soft_delete=soft_delete, session=session
            )
            
            # 同步删除播放记录
            if not soft_delete and count > 0:
                 watch_history_logic = WatchHistoryLogic()
                 await watch_history_logic.delete_by_filter(asset_ids=asset_ids, session=session)

        # 硬删除：本地文件清理
        if not soft_delete and count:
            for asset in assets:
                if asset.store_type == AssetStoreType.LOCAL and asset.actual_path:
                    self.file_logic.delete_file(os.path.join(asset.library_id, asset.actual_path))

        return count

    @service_handler(action="delete_movie_asset")
    async def delete_movie_asset(
        self,
        asset_id: str,
        *,
        current_user,
        soft_delete: bool = True,
    ) -> bool:
        asset = await self.logic.get_asset(asset_id)
        library = await self.library_logic.get_library(asset.library_id)
        await self._ensure_user_edit_permission(current_user, library)

        # 硬删除需要先取详情
        asset: Optional[AssetRead] = None
        if not soft_delete:
            asset = await self.logic.get_asset(asset_id)

        async with self.logic.repo.transaction() as session:
            ok = await self.logic.delete_asset(asset_id, soft_delete=soft_delete, session=session)
            
            # 同步删除播放记录
            if not soft_delete and ok:
                 watch_history_logic = WatchHistoryLogic()
                 await watch_history_logic.delete_by_filter(asset_ids=[asset_id], session=session)

        # 硬删除：本地文件清理
        if ok and not soft_delete and asset and asset.store_type == AssetStoreType.LOCAL and asset.actual_path:
            self.file_logic.delete_file(os.path.join(library.id, asset.actual_path))

        return ok

    @service_handler(action="restore_movie_assets")
    async def restore_movie_assets(
        self,
        asset_ids: List[str],
        *,
        current_user,
    ) -> List[AssetRead]:
        assets_for_check = await self.logic.get_assets(asset_ids)
        lib_ids = set(a.library_id for a in assets_for_check)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_edit_permission(current_user, lib)
        # 执行恢复后，统一返回 Model 层模型
        await self.logic.restore_assets(asset_ids)
        restored = await self.logic.get_assets(asset_ids)
        return restored

    @service_handler(action="upload_movie_asset")
    async def upload_movie_asset(
        self,
        data: AssetCreate,
        *,
        current_user,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[AssetRead, Dict[str, Any]]:
        library = await self.library_logic.get_library(data.library_id)
        await self._ensure_user_edit_permission(current_user, library)
        context = context or {}
        file = context.get("file")
        url = context.get("url")
        local_path = context.get("local_path")
        source_ext = context.get("source_ext")

        sources = [src for src in (file, url, local_path) if src is not None]
        if len(sources) != 1:
            raise ValueError("必须且仅提供其一：file / url / local_path")

        movie_id = data.movie_id
        asset_type = data.type
        name = data.name
        
        # 2) 计算保存路径与扩展名
        save_path = os.path.join(library.id, movie_id)
        if asset_type == AssetType.VIDEO:
            save_path = os.path.join(save_path, AssetType.VIDEO.value)
            save_ext = source_ext if source_ext else "mp4"
        elif asset_type == AssetType.SUBTITLE:
            save_path = os.path.join(save_path, AssetType.SUBTITLE.value)
            save_ext = source_ext if source_ext else "srt"
        elif asset_type == AssetType.IMAGE:
            save_path = os.path.join(save_path, AssetType.IMAGE.value)
            save_ext = source_ext if source_ext else "jpg"
        else:
            raise ValueError("不支持的资产类型")

        if file is not None:
            dest_path, save_name, actual_path = self.file_logic.smart_save_upload_to_library(
                file, save_path, save_ext
            )
        elif url is not None:
            dest_path, save_name, actual_path = self.file_logic.smart_download_file_to_library(
                url, save_path, save_ext
            )
        else:
            dest_path, save_name, actual_path = self.file_logic.smart_copy_file_to_library(
                local_path, save_path, save_ext
            )

        if dest_path.startswith(f"{library.id}/"):
            dest_path = dest_path.split("/", 1)[1]
        if actual_path.startswith(f"{library.id}/"):
            actual_path = actual_path.split("/", 1)[1]

        payload = AssetCreate(
            library_id=library.id,
            movie_id=movie_id,
            type=asset_type,
            name=name or save_name,
            store_type=AssetStoreType.LOCAL,
            path=dest_path,
            actual_path=actual_path,
        )
        created = await self.logic.create_asset(payload)

        tasks: Dict[str, Any] = {}

        msg_id = await send_task(
            "extract_metadata",
            {
                "target_kind": "movie_asset",
                "target_id": created.id,
                "target_info": created,
            },
            TaskPriority.HIGH,
        )
        tasks["extract_metadata"] = msg_id

        if asset_type in [AssetType.VIDEO, AssetType.IMAGE]:
            msg_id2 = await send_task(
                "generate_thumb_sprite",
                {
                    "target_kind": "movie_asset",
                    "target_id": created.id,
                    "target_info": created,
                    "kind": asset_type.value,
                },
                TaskPriority.HIGH,
            )
            tasks["generate_thumb_sprite"] = msg_id2

        return created, tasks

    @service_handler(action="list_movies_assets")
    async def list_movies_assets(
        self, movie_ids: List[str], *, current_user
    ) -> List[AssetRead]:
        results = await self.logic.list_movies_assets(movie_ids)
        return results

    @service_handler(action="list_movie_assets_page")
    async def list_movie_assets_page(
        self,
        movie_id: str,
        *,
        page: int = 1,
        size: int = 20,
        current_user,
    ):
        movie = await self.movie_logic.get_movie(movie_id)
        library = await self.library_logic.get_library(movie.library_id)
        await self._ensure_user_read_permission(current_user, library)
        page_result = await self.logic.search_assets(
            query=None,
            movie_id=movie_id,
            asset_type=None,
            page=page,
            size=size,
        )
        return page_result

    @service_handler(action="list_all_assets_page")
    async def list_all_assets_page(
        self,
        *,
        page: int = 1,
        size: int = 20,
        current_user,
    ):
        if current_user.role != UserRole.ADMIN:
            raise ForbiddenError("仅管理员可查看所有资产")

        return await self.logic.search_assets(
            query=None,
            movie_id=None,
            asset_type=None,
            page=page,
            size=size,
        )

    @service_handler(action="list_recycle_bin_assets")
    async def list_recycle_bin_assets(
        self,
        page: int = 1,
        size: int = 20,
        *,
        current_user,
    ):
        # 1. Get accessible libraries
        lib_ids = await self.library_logic.list_accessible_library_ids(
            role=current_user.role,
            user_id=current_user.id
        )
        
        if not lib_ids:
             return AssetPageResult(items=[], total=0, page=page, size=size, pages=0)

        return await self.logic.search_assets(
            is_deleted=True,
            library_ids=lib_ids,
            page=page,
            size=size
        )

    @service_handler(action="list_asset_thumbnails_signed")
    async def list_asset_thumbnails_signed(
        self,
        asset_ids: List[str],
        *,
        current_user,
    ) -> List[str]:
        assets = await self.logic.get_assets(asset_ids)
        lib_ids = set(a.library_id for a in assets)
        for lib_id in lib_ids:
            lib = await self.library_logic.get_library(lib_id)
            await self._ensure_user_read_permission(current_user, lib)

        signed_urls: List[str] = []
        for a in assets:
            if a.type not in (AssetType.VIDEO, AssetType.IMAGE):
                continue
            try:
                url, _ = self.file_logic.get_asset_thumbnail_signed_url(a.library_id, a.path)
                signed_urls.append(url)
            except Exception as e:
                self.logger.warning(f"生成电影资产缩略图签名失败: asset_id={a.id}, error={e}")
        return signed_urls

    @service_handler(action="get_movie_asset_file")
    async def get_asset_file(
        self,
        asset_id: str,
        *,
        transcode: bool = False,
        start: Optional[float] = None,
        duration: Optional[float] = None,
        target_bitrate_kbps: Optional[int] = None,
        target_resolution: Optional[str] = None,
        current_user,
    ):
        asset = await self.logic.get_asset(asset_id)
        if not asset:
            raise NotFoundError("资产不存在")
        library = await self.library_logic.get_library(asset.library_id)
        await self._ensure_user_read_permission(current_user, library)

        if asset.store_type != AssetStoreType.LOCAL:
            raise BadRequestError("暂不支持非本地存储访问")
        self.file_logic.check_file_exists(os.path.join(library.id, asset.path))

        # 图片：返回签名 URL
        if asset.type == AssetType.IMAGE:
            url, _ = self.file_logic.get_asset_signed_url(library.id, asset.path)
            return url

        # 视频：原生或实时转码
        if asset.type == AssetType.VIDEO:
            if not transcode:
                url, _ = self.file_logic.get_asset_signed_url(library.id, asset.path)
                return url

            # 转码模式：放宽 start/duration 限制，支持流式传输
            start_ts = start if (start is not None and start >= 0) else 0
            
            vf_args: List[str] = []
            if target_resolution:
                try:
                    w_str, h_str = target_resolution.lower().split("x")
                    w = int(w_str)
                    h = int(h_str)
                    if w <= 0 or h <= 0:
                        raise ValueError()
                    w -= (w % 2)
                    h -= (h % 2)
                    if w == 0 or h == 0:
                        raise ValueError()
                    vf_args = ["-vf", f"scale={w}:{h}"]
                except Exception:
                    raise BadRequestError("目标分辨率格式非法，应为 WxH，例如 1920x1080")

            br_args: List[str] = []
            if not vf_args and target_bitrate_kbps:
                kbps = int(target_bitrate_kbps)
                if kbps < 64 or kbps > 100000:
                    raise BadRequestError("目标码率范围非法（64~100000 kbps）")
                br_args = [
                    "-b:v", f"{kbps}k",
                    "-maxrate", f"{kbps}k",
                    "-bufsize", f"{max(128, kbps * 2)}k",
                ]

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", str(start_ts),
                "-i", self.file_logic._get_asset_file_path(library.id, asset.path),
            ]
            
            if duration is not None and duration > 0:
                cmd.extend(["-t", str(duration)])

            cmd.extend([
                "-vcodec", "libx264",
                "-acodec", "aac",
                "-preset", "veryfast",
                "-movflags", "frag_keyframe+empty_moov",
                "-pix_fmt", "yuv420p",
            ])
            
            cmd.extend(vf_args)
            cmd.extend(br_args)
            
            cmd.extend([
                "-f", "mp4",
                "pipe:1",
            ])
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def _stream():
                try:
                    while True:
                        chunk = process.stdout.read(64 * 1024)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    try:
                        process.stdout.close()
                    except Exception:
                        pass
                    try:
                        process.kill()
                    except Exception:
                        pass

            return StreamingResponse(_stream(), media_type="video/mp4")

        raise BadRequestError("仅支持图片(IMAGE)与视频(VIDEO)资产类型")
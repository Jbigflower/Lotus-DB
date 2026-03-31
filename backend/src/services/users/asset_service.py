# 顶部导入替换为用户文件操作逻辑类
import os
from typing import Optional, List, Dict, Set, Tuple, Any
from src.logic import UserAssetLogic, MovieLogic, LibraryLogic, WatchHistoryLogic
from src.logic.movies.asset_logic import MovieAssetLogic
from src.logic.file.film_asset_file_ops import FilmAssetFileOps
from src.models import (
    PartialPageResult,
    UserAssetType,
    UserAssetInDB,
    UserAssetCreate,
    UserAssetUpdate,
    UserAssetPageResult,
    UserAssetRead,
    UserRole,
    AssetStoreType,
    TaskPriority,
)

from src.logic.file.user_asset_file_ops import UserAssetFileOps
from src.core.handler import service_handler
from config.logging import get_service_logger
from src.core.exceptions import NotFoundError, ForbiddenError
from src.async_worker.core import send_task
from starlette.responses import StreamingResponse
from src.core.exceptions import BadRequestError
import subprocess


class AssetService:
    def __init__(self):
        self.logic = UserAssetLogic()
        self.library_logic = LibraryLogic()
        self.movie_logic = MovieLogic()
        self.movie_asset_logic = MovieAssetLogic()
        self.file_logic = UserAssetFileOps()
        self.logger = get_service_logger("asset_service")

    async def _ensure_user_read_permission(self, asset_ids: List[str], current_user) -> None:
        """检查用户是否有读取用户资产的权限"""
        assets = await self.logic.get_assets(asset_ids)
        if current_user.role == UserRole.ADMIN:
            return
        if current_user.role == UserRole.USER:
            for asset in assets:
                if current_user.id != asset.user_id and asset.is_public == False:
                    raise ForbiddenError("当前用户权限不可读取其他用户私有资产")
        if current_user.role == UserRole.GUEST:
            for asset in assets:
                if asset.is_public == False:
                    raise ForbiddenError("访客不可读取私有资产")

    async def _ensure_user_edit_permission(self, asset_ids: List[str], current_user) -> None:
        """检查用户是否有操作用户资产的权限"""
        if current_user.role == UserRole.GUEST:
            raise ForbiddenError("访客不可编辑资产")

        # 修复：批量校验应使用 get_assets
        assets = await self.logic.get_assets(asset_ids)
        if current_user.role == UserRole.ADMIN:
            return
        if current_user.role == UserRole.USER:
            for asset in assets:
                if current_user.id != asset.user_id:
                    raise ForbiddenError("当前用户权限不可编辑其他用户资产")

    async def _ensure_user_create_permission(self, movie_ids, current_user) -> None:
        """检查用户是否有创建用户资产的权限，#TODO 暂时只支持对 同一媒体库下媒体进行资产创建"""
        # 排除访客
        if current_user.role == UserRole.GUEST:
            raise ForbiddenError("访客不可创建资产")

        # 检查关联的影片是否存在
        movies = await self.movie_logic.get_movies(movie_ids)

        # 跳过管理员
        if current_user.role == UserRole.ADMIN:
            return
        # 普通用户
        library_ids = set()
        for movie in movies:
            library_ids.add(movie.library_id)
        library_ids = list(library_ids)
        for library_id in library_ids:
            library = await self.library_logic.get_library(library_id)
            if library.is_public is False and library.user_id != current_user.id:
                raise ForbiddenError("当前用户权限不可触发写操作")

    @service_handler(action="list_assets")
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
        *,
        current_user=None,
    ) -> [PartialPageResult | UserAssetPageResult]:
        if is_public is not True and current_user.role == UserRole.GUEST:
            raise ForbiddenError("访客只能读取公共资产")
        if user_id is None:
            if current_user.role == UserRole.USER:
                user_id = current_user.id

        return await self.logic.list_assets(
            query=query,
            user_id=user_id,
            movie_ids=movie_ids,
            asset_type=asset_type,
            tags=tags,
            is_public=is_public,
            page=page,
            size=size,
            sort=sort,
            projection=projection,
            session=session,
            is_deleted=is_deleted,
        )

    @service_handler(action="restore_user_assets")
    async def restore_user_assets(
        self, asset_ids: List[str], *, current_user=None
    ) -> List[UserAssetRead]:
        await self._ensure_user_edit_permission(asset_ids, current_user=current_user)
        await self.logic.restore_assets(asset_ids)
        return await self.logic.get_assets(asset_ids)

    @service_handler(action="get_assets")
    async def get_assets(
        self,
        asset_ids: List[str],
        *,
        current_user=None,
    ) -> Optional[List[UserAssetRead]]:
        await self._ensure_user_read_permission(asset_ids, current_user)
        result = await self.logic.get_assets(asset_ids)
        return result

    @service_handler(action="get_asset")
    async def get_asset(
        self,
        asset_id: str,
        *,
        current_user=None,
    ) -> Optional[UserAssetRead]:
        await self._ensure_user_read_permission([asset_id], current_user)
        result = await self.logic.get_asset(asset_id)
        return result

    @service_handler(action="get_movie_assets")
    async def get_movie_assets(
        self, movie_id: str, *, current_user, asset_type=None
    ) -> List[UserAssetRead]:
        if current_user.role == UserRole.GUEST:
            results = await self.logic.list_assets(
                movie_ids=[movie_id], asset_type=asset_type, is_public=True,
                page=1, size=1000
            )
            
        elif current_user.role == UserRole.ADMIN:
            results = await self.logic.list_assets(
                movie_ids=[movie_id], asset_type=asset_type,
                page=1, size=1000
            )
        else:
            results = await self.logic.list_assets(
                movie_ids=[movie_id], user_id=current_user.id, asset_type=asset_type,
                page=1, size=1000
            )
        return results.items if results else None


    @service_handler(action="上传用户资产")
    async def upload_user_asset(
        self,
        data: UserAssetCreate,
        *,
        current_user,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[UserAssetRead, Dict[str, Any]]:
        # 1) 权限与参数校验
        context = context or {}
        file = context.get("file")
        local_path = context.get("local_path")
        sources = [src for src in (file, local_path) if src is not None]
        if len(sources) != 1:
            raise ValueError("必须且仅提供其一：file / local_path")

        movie_ids = [data.movie_id] + (data.related_movie_ids or [])
        await self._ensure_user_create_permission(movie_ids, current_user)

        # 2) 计算保存路径与扩展名
        save_path = os.path.join(current_user.id, data.movie_id)
        if data.type == UserAssetType.CLIP:
            save_path = os.path.join(save_path, UserAssetType.CLIP.value)
            save_ext = "mp4"
        elif data.type == UserAssetType.SCREENSHOT:
            save_path = os.path.join(save_path, UserAssetType.SCREENSHOT.value)
            save_ext = "jpg"
        else:
            # 当前仅支持文件型资产（截图/剪辑）；文本类资产可后续扩展
            raise ValueError("不支持的资产类型")

        # 3) 文件落地（上传/拷贝）
        if file is not None:
            dest_path, save_name, actual_path = self.file_logic.smart_save_upload_to_user(file, save_path, save_ext)
        else:
            dest_path, save_name, actual_path = self.file_logic.smart_copy_file_to_user(local_path, save_path, save_ext)

        if dest_path.startswith(f"{current_user.id}/"):
            dest_path = dest_path.split("/", 1)[1]
        if actual_path.startswith(f"{current_user.id}/"):
            actual_path = actual_path.split("/", 1)[1]

        # 4) 填充必需字段并创建
        data.path = dest_path
        data.actual_path = actual_path
        data.name = save_name if (data.name is None or not data.name.strip()) else data.name
        data.user_id = current_user.id

        created = await self.logic.create_asset(data)

        # 5) 异步任务（提取元数据 / 生成雪碧图）
        tasks: Dict[str, Any] = {}
        meta_task_id = await send_task(
            "extract_metadata",
            {"target_kind": "user_asset", "target_id": created.id, "target_info": created},
            TaskPriority.HIGH,
        )
        tasks["extract_metadata"] = meta_task_id

        if data.type in (UserAssetType.CLIP, UserAssetType.SCREENSHOT):
            sprite_task_id = await send_task(
                "generate_thumb_sprite",
                {"target_kind": "user_asset", "target_id": created.id, "target_info": created, "kind": data.type.value},
                TaskPriority.HIGH,
            )
            tasks["generate_thumb_sprite"] = sprite_task_id

        return created, tasks

    @service_handler(action="update_user_asset")
    async def update_user_asset(
        self, asset_id: str, patch: UserAssetUpdate, *, current_user
    ) -> UserAssetRead:
        await self._ensure_user_edit_permission([asset_id], current_user=current_user)
        patch_dict = patch.model_dump(exclude_unset=True)
        updated = await self.logic.update_asset(asset_id, patch_dict)
        return updated

    @service_handler(action="delete_user_asset")
    async def delete_user_assets(
        self, asset_ids: List[str], *, soft_delete: bool = True, current_user=None
    ) -> int:
        await self._ensure_user_edit_permission(asset_ids, current_user=current_user)
        
        # 如果是硬删除，先查询资产以清理文件
        assets_to_delete = []
        if not soft_delete:
            assets_to_delete = await self.logic.get_assets(asset_ids)

        # 统一返回删除成功数量（int），供路由层组装 message/success/failed
        count = await self.logic.delete_assets(asset_ids, soft_delete=soft_delete)
        
        # 同步删除播放记录
        if not soft_delete and count > 0:
             watch_history_logic = WatchHistoryLogic()
             await watch_history_logic.delete_by_filter(asset_ids=asset_ids)

        # 硬删除：清理本地文件
        if not soft_delete and count > 0:
            for asset in assets_to_delete:
                if asset.store_type == AssetStoreType.LOCAL and asset.actual_path:
                    try:
                        # 构造完整路径并删除
                        full_path = self.file_logic._get_asset_file_path(asset.user_id, asset.actual_path)
                        if os.path.exists(full_path):
                            os.remove(full_path)
                    except Exception as e:
                        self.logger.warning(f"Failed to delete file for asset {asset.id}: {e}")
        
        return count

    @service_handler(action="update_user_assets_active_status")
    async def update_user_assets_active_status(
        self, asset_ids: List[str], is_public: bool, *, current_user=None
    ) -> List[UserAssetRead]:
        await self._ensure_user_edit_permission(asset_ids, current_user=current_user)
        return await self.logic.update_user_assets_activity(asset_ids, is_public)

    @service_handler(action="list_isolated_assets")
    async def list_isolated_assets(self, current_user=None) -> List[UserAssetRead]:
        if current_user.role == UserRole.GUEST:
            return []
        elif current_user.role == UserRole.USER:
            return await self.logic.list_isolated_assets(current_user.id)
        else:
            return await self.logic.list_isolated_assets()

    @service_handler(action="allocate_assets")
    async def allocate_assets(
        self, allocate_map: Dict[str, List[str]], current_user=None
    ) -> List[UserAssetRead]:
        if current_user.role == UserRole.GUEST:
            raise ForbiddenError("Guest user cannot allocate assets")

        # 检查所有的 value 即 movie-ids 是否存在
        movie_ids = [
            movie_id for movie_ids in allocate_map.values() for movie_id in movie_ids
        ]
        exist_movie_ids = await self.movie_logic.check_movies_exist_fast(movie_ids)
        if not exist_movie_ids:
            detail_result = await self.movie_logic.check_movies_exist_detail(movie_ids)
            raise NotFoundError(
                f"Some movie ids do not exist: {set(movie_ids) - set(detail_result.keys())}"
            )

        elif current_user.role == UserRole.USER:
            await self._ensure_user_edit_permission(
                allocate_map.keys(), current_user=current_user
            )
        return await self.logic.allocate_assets(allocate_map)

    @service_handler(action="list_user_asset_thumbnails_signed")
    async def list_user_asset_thumbnails_signed(
        self,
        asset_ids: List[str],
        *,
        current_user,
    ) -> List[str]:
        # 权限：批量资产可读
        await self._ensure_user_read_permission(asset_ids, current_user)
        assets = await self.logic.get_assets(asset_ids)

        signed_urls: List[str] = []
        for a in assets:
            # 仅截图/剪辑支持缩略图
            if a.type not in (UserAssetType.SCREENSHOT, UserAssetType.CLIP):
                continue
            try:
                # 1) 计算缩略图的实际路径（使用path：逻辑地址，而不是actual：实际地址）
                url, _ = self.file_logic.get_asset_thumbnail_signed_url(a.user_id, a.path)
                signed_urls.append(url)
            except Exception as e:
                self.logger.warning(f"生成用户资产缩略图签名失败: asset_id={a.id}, error={e}")
        return signed_urls

    @service_handler(action="get_user_asset_file")
    async def get_user_asset_file(
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
        await self._ensure_user_read_permission([asset_id], current_user)
        asset = await self.logic.get_asset(asset_id)
        if not asset:
            raise NotFoundError("资产不存在")

        if asset.store_type != AssetStoreType.LOCAL:
            raise BadRequestError("暂不支持非本地存储访问")

        # 检查文件是否存在
        self.file_logic.check_file_exists(os.path.join(asset.user_id, asset.path))
        
        # 图片（截图）：返回签名 URL
        if asset.type == UserAssetType.SCREENSHOT:
            url, _ = self.file_logic.get_asset_signed_url(asset.user_id, asset.path)
            return url

        # 视频（剪辑）：原生或实时转码
        if asset.type == UserAssetType.CLIP:
            if not transcode:
                url, _ = self.file_logic.get_asset_signed_url(asset.user_id, asset.path)
                return url

            if start is None or duration is None or start < 0 or duration <= 0:
                raise BadRequestError("实时转码需要提供合法的 start(>=0) 和 duration(>0)")

            # 解析分辨率（若提供）
            vf_args: List[str] = []
            if target_resolution:
                try:
                    w_str, h_str = target_resolution.lower().split("x")
                    w = int(w_str)
                    h = int(h_str)
                    if w <= 0 or h <= 0:
                        raise ValueError()
                    # 修正为偶数
                    w -= (w % 2)
                    h -= (h % 2)
                    if w == 0 or h == 0:
                        raise ValueError()
                    vf_args = ["-vf", f"scale={w}:{h}"]
                except Exception:
                    raise BadRequestError("目标分辨率格式非法，应为 WxH，例如 1280x720")

            # 码率（仅当未指定分辨率时生效）
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

            abs_path = self.file_logic._get_asset_file_path(asset.user_id, asset.actual_path)
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", str(start),
                "-i", abs_path,
                "-t", str(duration),
                "-vcodec", "libx264",
                "-acodec", "aac",
                "-preset", "veryfast",
                "-movflags", "frag_keyframe+empty_moov",
                "-pix_fmt", "yuv420p",
            ] + vf_args + br_args + [
                "-f", "mp4",
                "pipe:1",
            ]
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

    @service_handler(action="create_screenshot_from_movie_asset")
    async def create_screenshot_from_movie_asset(
        self,
        *,
        asset_id: str,
        movie_id: str,
        time: float,
        name: Optional[str] = None,
        is_public: bool = False,
        tags: Optional[List[str]] = None,
        current_user,
    ) -> tuple[UserAssetRead, Dict[str, Any]]:
        raise BadRequestError("后端截图功能已停用，请在前端截帧后使用上传接口保存")

        # 获取电影资产详情
        movie_asset = await self.movie_asset_logic.get_asset(asset_id)
        if not movie_asset:
            raise NotFoundError("电影资产不存在")

        if movie_asset.store_type != AssetStoreType.LOCAL:
            raise BadRequestError("暂不支持非本地存储截图生成")

        asset_ops = FilmAssetFileOps()
        asset_ops.check_file_exists(os.path.join(movie_asset.library_id, movie_asset.path))
        abs_path = asset_ops._get_asset_file_path(movie_asset.library_id, movie_asset.path)

        # 生成临时截图文件
        if time is None or time < 0:
            raise BadRequestError("截图时间点(time)非法")
        tmp_dir = os.path.join("/tmp", "lotus-screenshot")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_out = os.path.join(tmp_dir, f"shot_{current_user.id}_{movie_id}_{int(time)}.jpg")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(time),
            "-i", abs_path,
            "-frames:v", "1",
            "-q:v", "2",
            "-y", tmp_out,
        ]
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 0 or (not os.path.exists(tmp_out)):
            err = (process.stderr or b"").decode(errors="ignore")
            self.logger.error(f"截图生成失败: asset_id={asset_id}, time={time}, error={err}")
            raise BadRequestError("截图生成失败")

        # 保存到用户目录
        ops_user = UserAssetFileOps()
        save_path = os.path.join(current_user.id, movie_id, UserAssetType.SCREENSHOT.value)
        dest_path, save_name, actual_path = ops_user.smart_copy_file_to_user(tmp_out, save_path, "jpg")
        if dest_path.startswith(f"{current_user.id}/"):
            dest_path = dest_path.split("/", 1)[1]
        if actual_path.startswith(f"{current_user.id}/"):
            actual_path = actual_path.split("/", 1)[1]

        # 组装并创建用户资产
        ua = UserAssetCreate(
            movie_id=movie_id,
            type=UserAssetType.SCREENSHOT,
            name=name or save_name,
            related_movie_ids=[],
            tags=tags or [],
            is_public=is_public,
            permissions=[],
            path=dest_path,
            store_type=AssetStoreType.LOCAL,
            actual_path=actual_path,
            content=None,
            user_id=current_user.id,
        )
        created = await self.logic.create_asset(ua)

        # 异步任务：提取元数据与缩略图
        tasks: Dict[str, Any] = {}
        meta_task_id = await send_task(
            "extract_metadata",
            {"target_kind": "user_asset", "target_id": created.id, "src_path": actual_path},
            TaskPriority.HIGH,
        )
        tasks["extract_metadata"] = meta_task_id

        sprite_task_id = await send_task(
            "generate_thumb_sprite",
            {"target_kind": "user_asset", "target_id": created.id, "src_path": actual_path, "kind": UserAssetType.SCREENSHOT.value},
            TaskPriority.HIGH,
        )
        tasks["generate_thumb_sprite"] = sprite_task_id

        # 清理临时文件
        try:
            os.remove(tmp_out)
        except Exception:
            pass

        return created, tasks

    @service_handler(action="create_text_user_asset")
    async def create_text_user_asset(
        self,
        data: UserAssetCreate,
        *,
        current_user,
    ) -> UserAssetRead:
        if data.type not in (UserAssetType.NOTE, UserAssetType.REVIEW):
            raise BadRequestError("仅支持 note/review 类型")
        if data.content is None or not str(data.content).strip():
            raise BadRequestError("content 字段必填")

        movie_ids = [data.movie_id] + (data.related_movie_ids or [])
        await self._ensure_user_create_permission(movie_ids, current_user)

        if not data.name or not data.name.strip():
            preview = str(data.content).strip()
            data.name = preview[:20] if preview else "untitled"
        if not data.path or not data.path.strip():
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            data.path = os.path.join(data.movie_id, data.type.value, f"{ts}.md")
        if not data.store_type:
            data.store_type = AssetStoreType.LOCAL
        data.actual_path = None
        data.user_id = current_user.id

        created = await self.logic.create_asset(data)
        return created

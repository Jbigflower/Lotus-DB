# 模块顶部导入与调用修正
import os
import asyncio
from typing import Dict, Any
from src.logic.media.media_logic import (
    extract_media_metadata,
    generate_video_thumbnails_and_sprite,
    generate_image_thumbnail,
)
from src.logic.file.user_asset_file_ops import UserAssetFileOps
from src.logic.file.film_asset_file_ops import FilmAssetFileOps 
from src.core.handler import task_handler


UserOps = UserAssetFileOps()
FilmOps = FilmAssetFileOps()

# 保留原名：extract_metadata_task
@task_handler("提取媒体元数据")
async def extract_metadata_task(
    target_kind: str, target_id: str, target_info: Dict[str, Any]
) -> Dict[str, Any]:
    """提取媒体元数据任务"""
    
    print(f'extract_metadata_task: {target_kind}, {target_id}, {target_info}')

    if target_kind == "user_asset":
        from src.repos.mongo_repos.users.user_asset_repo import UserAssetRepo

        repo = UserAssetRepo()
        asset = await repo.find_by_id(target_id)
        asset_type = getattr(asset, "type", None)
        asset_type_value = asset_type.value if asset_type else "clip"

        media_path = UserOps._get_asset_file_path(target_info['user_id'], target_info['path'])
        meta: Dict[str, Any] = await asyncio.to_thread(extract_media_metadata, media_path)
        update_doc = {}
        update_doc.update(
            {
                "metadata.type": asset_type_value,
                "metadata.size": meta.get("size", 0),
            }
        )
        if asset_type_value == "clip":
            update_doc.update(
                {
                    "metadata.duration": meta.get("duration"),
                    "metadata.quality": meta.get("quality"),
                    "metadata.codec": meta.get("codec"),
                    "metadata.width": meta.get("width"),
                    "metadata.height": meta.get("height"),
                    "metadata.has_thumbnail": meta.get("has_thumbnail"),
                    "metadata.has_sprite": meta.get("has_sprite"),
                }
            )
        elif asset_type_value in ("screenshot", "image"):
            update_doc.update(
                {
                    "metadata.width": meta.get("width"),
                    "metadata.height": meta.get("height"),
                }
            )
        await repo.update_by_id(target_id, update_doc)

    elif target_kind == "movie_asset":
        from src.repos.mongo_repos.movies.asset_repo import AssetRepo
        from src.models import AssetType

        repo = AssetRepo()
        asset = await repo.find_by_id(target_id)
        asset_type = getattr(asset, "type", None)
        asset_type_value = asset_type.value if asset_type else AssetType.VIDEO.value
        
        media_path = FilmOps._get_asset_file_path(target_info['library_id'], target_info['path'])
        meta: Dict[str, Any] = await asyncio.to_thread(extract_media_metadata, media_path)
        update_doc = {"metadata.type": asset_type_value, "metadata.size": meta.get("size", 0),}
        if asset_type_value == AssetType.VIDEO.value:
            update_doc.update(
                {
                    "metadata.duration": meta.get("duration"),
                    "metadata.quality": meta.get("quality"),
                    "metadata.codec": meta.get("codec"),
                    "metadata.width": meta.get("width"),
                    "metadata.height": meta.get("height"),
                    "metadata.has_thumbnail": meta.get("has_thumbnail"),
                    "metadata.has_sprite": meta.get("has_sprite"),
                }
            )
        elif asset_type_value == AssetType.IMAGE.value:
            update_doc.update(
                {
                    "metadata.width": meta.get("width"),
                    "metadata.height": meta.get("height"),
                }
            )
        await repo.update_by_id(target_id, update_doc)
    return meta


# 保留原名：generate缩略图与雪碧图
@task_handler("生成缩略图与雪碧图")
async def generate_thumb_sprite_task(
    target_kind: str, target_id: str, target_info: Dict[str, Any], kind: str
) -> Dict[str, Any]:

    print(f'generate_thumb_sprite_task: {target_kind}, {target_id}, {target_info}, {kind}')

    result: Dict[str, Any] = {"has_thumbnail": False, "has_sprite": False}

    src_path, out_dir = "", ""
    if target_kind == "user_asset":
        src_path = UserOps._get_asset_file_path(target_info['user_id'], target_info['path'])
        out_dir = os.path.splitext(src_path)[0]
    elif target_kind == "movie_asset":
        src_path = FilmOps._get_asset_file_path(target_info['library_id'], target_info['path'])
        out_dir = os.path.splitext(src_path)[0]

    kind_lower = (kind or "").lower()
    if kind_lower in ("clip", "video"):

        await asyncio.to_thread(
            generate_video_thumbnails_and_sprite,
            src_path,
            out_dir,
            "clip",  # 这里使用 clip 以匹配逻辑层入参
            thumb_width=320,
            frame_count=12,
            sprite_cols=4,
        )
        result["has_thumbnail"] = True
        result["has_sprite"] = True

    elif kind_lower in ("image", "screenshot"):
        thumb_path = await asyncio.to_thread(
            generate_image_thumbnail, src_path, out_dir, kind_lower, 320
        )
        result["has_thumbnail"] = os.path.exists(thumb_path)
        result["has_sprite"] = False

    if target_kind == "user_asset":
        from src.repos.mongo_repos.users.user_asset_repo import UserAssetRepo

        repo = UserAssetRepo()
        await repo.update_by_id(
            target_id,
            {
                "metadata.has_thumbnail": result["has_thumbnail"],
                "metadata.has_sprite": result["has_sprite"],
            },
        )
    elif target_kind == "movie_asset":
        from src.repos.mongo_repos.movies.asset_repo import AssetRepo

        repo = AssetRepo()
        await repo.update_by_id(
            target_id,
            {
                "metadata.has_thumbnail": result["has_thumbnail"],
                "metadata.has_sprite": result["has_sprite"],
            },
        )
    return result

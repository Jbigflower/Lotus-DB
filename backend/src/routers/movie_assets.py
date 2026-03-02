from fastapi import (
    APIRouter,
    Depends,
    Request,
    Query,
    Path,
    Body,
    UploadFile,
    File,
    Form,
    HTTPException,
)
from typing import List, Optional
import os
from urllib.parse import urlparse

from src.core.dependencies import get_current_user
from src.models import AssetStoreType, AssetType, AssetUpdate, AssetCreate
from src.routers.schemas.asset import (
    AssetReadResponseSchema,
    AssetPageResultResponseSchema,
    AssetCreateRequestSchema,
    AssetUpdateRequestSchema,
)
from src.routers.schemas.user_asset import UserAssetIdsRequestSchema
from src.services import MovieAssetService
from src.core.handler import router_handler
from src.core.idempotency import idempotent
from config.logging import get_router_logger

router = APIRouter(prefix="/assets", tags=["Movies"])
asset_service = MovieAssetService()
logger = get_router_logger("movie_assets")

@router.get("/", response_model=AssetPageResultResponseSchema)
@router_handler(action="list_all_assets")
async def list_all_assets(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=200, description="每页数量"),
    current_user=Depends(get_current_user),
):
    return await asset_service.list_all_assets_page(
        page=page, size=size, current_user=current_user
    )


# 查找（Query）
@router.get("/recycle-bin", response_model=AssetPageResultResponseSchema)
@router_handler(action="list_recycle_bin_assets")
async def list_recycle_bin_assets(
    request: Request,
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=200, description="每页数量"),
    current_user=Depends(get_current_user),
):
    return await asset_service.list_recycle_bin_assets(
        page=page, size=size, current_user=current_user
    )


@router.get("/movies/{movie_id}", response_model=AssetPageResultResponseSchema)
@router_handler(action="list_movie_assets")
async def list_movie_assets(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=200, description="每页数量"),
    current_user=Depends(get_current_user),
):
    return await asset_service.list_movie_assets_page(
        movie_id, page=page, size=size, current_user=current_user
    )

@router.get("/{asset_id}", response_model=AssetReadResponseSchema)
@router_handler(action="get_asset")
async def get_asset(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    current_user=Depends(get_current_user),
):
    return await asset_service.get_asset(
        asset_id, current_user=current_user
    )


# 修改（Update）
@router.patch("/{asset_id}", response_model=AssetReadResponseSchema)
@router_handler(action="update_movie_asset")
async def update_movie_asset(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    patch: AssetUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    model_patch = AssetUpdate(**patch.model_dump(exclude_unset=True))
    return await asset_service.update_movie_asset(
        asset_id,
        model_patch,
        current_user=current_user,
    )

# 删除（Delete）
@router.delete("/bulk", response_model=dict)
@router_handler(action="delete_movie_assets_bulk")
async def delete_movie_assets(
    request: Request,
    body: UserAssetIdsRequestSchema = Body(..., description="资产ID列表"),
    soft_delete: bool = Query(True, description="是否软删除"),
    current_user=Depends(get_current_user),
):
    asset_ids = body.asset_ids
    success = await asset_service.delete_movie_assets(
        asset_ids,
        current_user=current_user,
        soft_delete=soft_delete,
    )
    failed = max(len(asset_ids) - success, 0)
    message = "删除完成" if failed == 0 else "部分资产删除失败"
    return {"message": message, "success": success, "failed": failed}

@router.delete("/{asset_id}", response_model=dict)
@router_handler(action="delete_movie_asset")
async def delete_movie_asset(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    soft_delete: bool = Query(True, description="是否软删除"),
    current_user=Depends(get_current_user),
):
    ok = await asset_service.delete_movie_asset(
        asset_id,
        current_user=current_user,
        soft_delete=soft_delete,
    )
    return {"message": "删除完成" if ok else "删除失败", "success": 1 if ok else 0, "failed": 0 if ok else 1}


# 重建（Rebuild / Restore）
@router.post("/restore", response_model=List[AssetReadResponseSchema])
@router_handler(action="restore_movie_assets_bulk")
async def restore_movie_assets(
    request: Request,
    body: UserAssetIdsRequestSchema = Body(..., description="资产ID列表"),
    current_user=Depends(get_current_user),
):
    asset_ids = body.asset_ids
    restored = await asset_service.restore_movie_assets(
        asset_ids,
        current_user=current_user,
    )
    return restored

# 新增（Create）
@router.post("/{movie_id}", response_model=dict)
@router_handler(action="create_movie_asset")
@idempotent()
async def create_movie_asset(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    library_id: str = Form(..., description="媒体库ID"),
    type: AssetType = Form(..., description="资产类型"),
    name: Optional[str] = Form(None, description="资产名称"),
    store_type: Optional[str] = Form("Local", description="资产存储"),  # TODO 后期存储扩展
    file: Optional[UploadFile] = File(None, description="媒体文件"),
    url: Optional[str] = Form(None, description="媒体文件可访问的 URL（http/https）"),
    local_path: Optional[str] = Form(None, description="服务端源文件绝对路径"),
    source_ext: Optional[str] = Form(None, description="源文件扩展名"),
    current_user=Depends(get_current_user),
):
    sources = [src for src in (file, url, local_path) if src is not None]
    if len(sources) != 1:
        raise HTTPException(status_code=400, detail="请提供且仅提供其一：file / url / local_path")

    if url is not None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=400, detail="非法 URL：仅支持 http/https")
    if local_path is not None:
        if not os.path.isabs(local_path) or not os.path.exists(local_path):
            raise HTTPException(status_code=400, detail="源文件路径不存在或不可访问（需绝对路径）")

    # 路由层：使用 schemas 入参并转换为 Model 层
    create_req = AssetCreateRequestSchema(
        movie_id=movie_id,
        type=type,
        name=name,
    ).model_dump()
    create_req['path'] = 'temp'
    create_req['library_id'] = library_id
    payload = AssetCreate(**create_req)
    ctx = {"file": file, "url": url, "local_path": local_path, "source_ext": source_ext}
    asset_model, task_info = await asset_service.upload_movie_asset(
        payload,
        context=ctx,
        current_user=current_user,
    )
    return {"asset": asset_model, "tasks": task_info}

@router.post("/thumbnails/sign", response_model=List[str])
@router_handler(action="get_asset_thumbnails_signed")
async def get_asset_thumbnails_signed(
    request: Request,
    body: UserAssetIdsRequestSchema = Body(..., description="资产ID列表"),
    current_user=Depends(get_current_user),
):
    return await asset_service.list_asset_thumbnails_signed(
        body.asset_ids,
        current_user=current_user,
    )

@router.get("/{asset_id}/file")
@router_handler(action="get_movie_asset_file")
async def get_movie_asset_file(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    transcode: bool = Query(False, description="是否实时转码"),
    start: Optional[float] = Query(None, ge=0, description="转码起始秒"),
    duration: Optional[float] = Query(None, ge=1, description="转码时长（秒）"),
    target_bitrate_kbps: Optional[int] = Query(None, ge=64, le=100000, description="目标视频码率（kbps），与分辨率二选一"),
    target_resolution: Optional[str] = Query(None, description="目标分辨率，例如 1280x720；与码率二选一"),
    current_user=Depends(get_current_user),
):
    return await asset_service.get_asset_file(
        asset_id,
        transcode=transcode,
        start=start,
        duration=duration,
        target_bitrate_kbps=target_bitrate_kbps,
        target_resolution=target_resolution,
        current_user=current_user,
    )
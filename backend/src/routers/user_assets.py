# 模块级：FastAPI 路由定义
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Query,
    Body,
    File,
    UploadFile,
    Form,
    Request,
)
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from src.core.dependencies import get_current_user  # 返回当前登录用户对象
from src.models import (
    UserAssetType,
    AssetStoreType,
    UserAssetUpdate,
    UserAssetCreate,
)
from src.services import AssetService
from src.core.handler import router_handler
from config.logging import get_router_logger, set_trace_id, get_trace_id
from src.core.idempotency import idempotent

from src.routers.schemas.user_asset import (
    UserAssetCreateRequestSchema,
    UserAssetUpdateRequestSchema,
    UserAssetReadResponseSchema,
    UserAssetPageResultResponseSchema,
    UserAssetIdsRequestSchema,
    UserAssetBatchUpdateRequestSchema,
    UserAssetSetActiveStatusRequestSchema,
    UserAssetAllocateRequestSchema,
    ScreenshotCreateRequestSchema,
)

router = APIRouter(prefix="/api/v1/user_assets", tags=["User_Assets"])
service = AssetService()
logger = get_router_logger("user_assets")


# -----------------------------
# 基础 - Ping
# -----------------------------
@router.get("/ping")
@router_handler(action="ping")
async def ping(request: Request):
    return {"status": "ok", "router": "User_Assets"}


# -----------------------------
# 分页查询用户资产（与 AssetService.list_assets 对齐）
# -----------------------------
# 查找（Query） - 分页列表
@router.get("/", response_model=UserAssetPageResultResponseSchema)
@router_handler(action="list_user_assets")
async def list_user_assets(
    request: Request,
    q: Optional[str] = Query(None, description="模糊搜索关键字"),
    movie_ids: Optional[List[str]] = Query(None, description="按电影ID列表筛选"),
    asset_type: Optional[List[UserAssetType]] = Query(None, description="按资产类型列表筛选"),
    tags: Optional[List[str]] = Query(None, description="标签筛选"),
    is_public: Optional[bool] = Query(None, description="按公开状态筛选"),
    is_deleted: Optional[bool] = Query(False, description="是否显示已删除"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=200, description="每页数量"),
    current_user=Depends(get_current_user),
):
    result = await service.list_assets(
        query=q,
        user_id=None,
        movie_ids=movie_ids,
        asset_type=asset_type or [],
        tags=tags,
        is_public=is_public,
        page=page,
        size=size,
        sort=None,
        projection=None,
        session=None,
        is_deleted=is_deleted,
        current_user=current_user,
    )
    return result


# -----------------------------
# 恢复用户资产
# -----------------------------
@router.post("/restore", response_model=List[UserAssetReadResponseSchema])
@router_handler(action="restore_user_assets")
async def restore_user_assets(
    request: Request,
    body: UserAssetIdsRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    return await service.restore_user_assets(
        body.asset_ids, current_user=current_user
    )


# -----------------------------
# 获取资产详情
# -----------------------------
@router.get("/{asset_id}", response_model=UserAssetReadResponseSchema)
@router_handler(action="get_asset_detail")
async def get_asset_detail(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    current_user=Depends(get_current_user),
):
    asset = await service.get_assets(asset_ids=[asset_id], current_user=current_user)
    if not asset or len(asset) == 0:
        raise HTTPException(status_code=404, detail="资产不存在或无权限访问")
    return asset[0]


# -----------------------------
# 上传用户资产（文件/本地路径，统一模型）
# -----------------------------
@router.post("/upload", response_model=dict)
@router_handler(action="upload_user_asset")
@idempotent()
async def upload_user_asset(
    request: Request,
    file: Optional[UploadFile] = File(None, description="上传的媒体文件"),
    local_path: Optional[str] = Form(None, description="本机已有文件路径"),
    movie_id: str = Form(..., description="关联电影ID"),
    type: UserAssetType = Form(..., description="资产类型"),
    store_type: AssetStoreType = Form(AssetStoreType.LOCAL, description="存储类型"),
    name: Optional[str] = Form(None, description="资源名称（可选）"),
    is_public: Optional[bool] = Form(False, description="是否公开"),
    tags: Optional[List[str]] = Form(None, description="标签（多值表单）"),
    related_movie_ids: Optional[List[str]] = Form(None, description="关联的其他电影ID（多值表单）"),
    content: Optional[str] = Form(None, description="文本内容（仅文本类资产需要）"),
    current_user=Depends(get_current_user),
):
    if file is None and not local_path:
        raise HTTPException(status_code=400, detail="必须提供 file 或 local_path 之一")

    # 路由层：用 schemas 校验，并转换为 Model；填充默认值
    create_req = UserAssetCreateRequestSchema(
        movie_id=movie_id,
        type=type,
        store_type=store_type,
        name=name,
        is_public=is_public or False,
        tags=tags or [],
        related_movie_ids=related_movie_ids or [],
        content=content,
    ).model_dump()

    # 必填但无法直接赋值的字段：由服务层/文件操作填充，这里先给占位默认值
    create_req["user_id"] = current_user.id
    create_req["path"] = "temp"
    create_req["name"] = create_req.get("name") or "pending"

    payload = UserAssetCreate(**create_req)
    ctx = {"file": file, "local_path": local_path}

    asset_model, task_info = await service.upload_user_asset(
        payload,
        context=ctx,
        current_user=current_user,
    )
    return {"asset": asset_model, "tasks": task_info}


@router.post("/text", response_model=UserAssetReadResponseSchema)
@router_handler(action="create_text_user_asset")
async def create_text_user_asset(
    request: Request,
    body: UserAssetCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    if body.type not in (UserAssetType.NOTE, UserAssetType.REVIEW):
        raise HTTPException(status_code=400, detail="仅支持 note/review 类型")
    if body.content is None or not str(body.content).strip():
        raise HTTPException(status_code=400, detail="content 字段必填")

    data = body.model_dump()
    data["user_id"] = current_user.id
    if not data.get("name"):
        preview = str(data.get("content") or "").strip()
        data["name"] = (preview[:20] or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    if not data.get("path"):
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        folder = body.type.value
        data["path"] = f"{body.movie_id}/{folder}/{ts}.md"
    if not data.get("store_type"):
        data["store_type"] = AssetStoreType.LOCAL
    data["actual_path"] = None

    payload = UserAssetCreate(**data)
    created = await service.create_text_user_asset(payload, current_user=current_user)
    return created


# -----------------------------
# 单资产更新（统一模型）
# -----------------------------
@router.patch("/{asset_id}", response_model=UserAssetReadResponseSchema)
@router_handler(action="update_user_asset")
async def update_user_asset(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    patch: UserAssetUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    model_patch = UserAssetUpdate(**patch.model_dump(exclude_unset=True))
    updated = await service.update_user_asset(asset_id, model_patch, current_user=current_user)
    return updated


# -----------------------------
# 单资产删除
# -----------------------------
@router.delete("/{asset_id}", response_model=dict)
@router_handler(action="delete_user_asset")
async def delete_user_asset(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    soft_delete: bool = Query(True, description="是否软删除"),
    current_user=Depends(get_current_user),
):
    success = await service.delete_user_assets(
        [asset_id], current_user=current_user, soft_delete=soft_delete
    )
    failed = 0 if success == 1 else 1
    message = "删除完成" if success == 1 else "删除失败"
    return {"message": message, "success": success, "failed": failed}


# -----------------------------
# 批量删除
# -----------------------------
@router.delete("/", response_model=dict)
@router_handler(action="delete_user_assets_batch")
async def delete_user_assets_batch(
    request: Request,
    body: UserAssetIdsRequestSchema = Body(...),
    soft_delete: bool = Query(True, description="是否软删除"),
    current_user=Depends(get_current_user),
):
    asset_ids = body.asset_ids
    success = await service.delete_user_assets(
        asset_ids, current_user=current_user, soft_delete=soft_delete
    )
    failed = max(len(asset_ids) - success, 0)
    message = "删除完成" if failed == 0 else "部分资产删除失败"
    return {"message": message, "success": success, "failed": failed}


# -----------------------------
# 批量设置公开状态
# -----------------------------
@router.patch("/active_status", response_model=List[UserAssetReadResponseSchema])
@router_handler(action="update_user_assets_active_status")
async def update_user_assets_active_status(
    request: Request,
    data: UserAssetSetActiveStatusRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    return await service.update_user_assets_active_status(
        data.asset_ids, data.is_public, current_user=current_user
    )


# -----------------------------
# 孤立资产列表（仅非访客）
# -----------------------------
@router.get("/isolated", response_model=List[UserAssetReadResponseSchema])
@router_handler(action="list_isolated_assets")
async def list_isolated_assets(
    request: Request,
    current_user=Depends(get_current_user),
):
    return await service.list_isolated_assets(current_user=current_user)


# -----------------------------
# 资产分配（资产ID → 电影ID列表）
# -----------------------------
@router.post("/allocate", response_model=List[UserAssetReadResponseSchema])
@router_handler(action="allocate_assets")
async def allocate_assets(
    request: Request,
    data: UserAssetAllocateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    # 服务层需要 current_user 做权限校验
    return await service.allocate_assets(data.allocate_map, current_user=current_user)


# -----------------------------
# 从电影资产生成截图（保存为用户资产）
# -----------------------------
@router.post("/screenshot", response_model=dict)
@router_handler(action="create_screenshot_from_movie_asset")
async def create_screenshot_from_movie_asset(
    request: Request,
    body: ScreenshotCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    raise HTTPException(
        status_code=410,
        detail="后端截图功能已停用，请在前端截帧后使用 /api/v1/user_assets/upload 上传保存",
    )


# ---- 用户资产缩略图签名（批量） ---- #
@router.post("/thumbnails/sign", response_model=List[str])
@router_handler(action="get_user_asset_thumbnails_signed")
async def get_user_asset_thumbnails_signed(
    request: Request,
    body: UserAssetIdsRequestSchema = Body(..., description="资产ID列表"),
    current_user=Depends(get_current_user),
):
    return await service.list_user_asset_thumbnails_signed(
        body.asset_ids,
        current_user=current_user,
    )

@router.get("/{asset_id}/file")
@router_handler(action="get_user_asset_file")
async def get_user_asset_file(
    request: Request,
    asset_id: str = Path(..., description="资产ID"),
    transcode: bool = Query(False, description="是否实时转码"),
    start: Optional[float] = Query(None, ge=0, description="转码起始秒"),
    duration: Optional[float] = Query(None, ge=1, description="转码时长（秒）"),
    target_bitrate_kbps: Optional[int] = Query(None, ge=64, le=100000, description="目标视频码率（kbps），与分辨率二选一"),
    target_resolution: Optional[str] = Query(None, description="目标分辨率，例如 1280x720；与码率二选一"),
    current_user=Depends(get_current_user),
):
    return await service.get_user_asset_file(
        asset_id,
        transcode=transcode,
        start=start,
        duration=duration,
        target_bitrate_kbps=target_bitrate_kbps,
        target_resolution=target_resolution,
        current_user=current_user,
    )

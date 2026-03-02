from fastapi import APIRouter, Depends, Body, Path, Query, Request, UploadFile, File
from typing import List, Optional, Dict, Any, Tuple

from src.core.dependencies import get_current_user
from src.models import (
    LibraryBase,
    LibraryUpdate,
    LibraryRead,
    LibraryPageResult,
    LibraryType,
    LibraryCreate,
)
from src.routers.schemas.library import (
    LibraryCreateRequestSchema,
    LibraryPageResultResponseSchema,
    LibraryReadResponseSchema,
    LibraryUpdateRequestSchema,
)
from src.services import LibraryService
from src.core.handler import router_handler
from config.logging import get_router_logger
from src.core.idempotency import idempotent
from src.agent.tools.builders import build_library_create_payload

logger = get_router_logger("libraries")

router = APIRouter(prefix="/api/v1/libraries", tags=["Libraries"])
service = LibraryService()


# ---- 状态相关 ---- #
# ---- 获取当前库 ----- #
@router.get("/current", response_model=Optional[LibraryReadResponseSchema])
@router_handler(action="get_current_library")
async def get_current_library(
    request: Request,
    current_user=Depends(get_current_user),
):
    raise HTTPException(status_code=410, detail="接口已下线：请使用显式 library_id 或资源派生")

# ---- 进入库 ----- #
@router.post("/{library_id}/enter", response_model=LibraryReadResponseSchema)
@router_handler(action="enter_library")
async def enter_library(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    current_user=Depends(get_current_user),
):
    raise HTTPException(status_code=410, detail="接口已下线：无需进入库，显式传参即可")

# ---- 退出库 ----- #
@router.post("/exit", response_model=Dict[str, Any])
@router_handler(action="exit_library")
async def exit_library(
    request: Request,
    current_user=Depends(get_current_user),
):
    raise HTTPException(status_code=410, detail="接口已下线：无需退出库，显式传参即可")

# ---- 查询（Query） ---- #
@router.get("/", response_model=LibraryPageResultResponseSchema)
@router_handler(action="list_libraries")
async def list_libraries(
    request: Request,
    query: Optional[str] = Query(None, description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页大小"),
    library_type: LibraryType = Query(..., description="媒体库类型"),
    is_active: Optional[bool] = Query(True, description="是否激活"),
    is_deleted: Optional[bool] = Query(False, description="是否已删除"),
    auto_import: Optional[bool] = Query(None, description="是否自动导入"),
    only_me: bool = Query(False, description="仅返回当前用户的库"),
    current_user=Depends(get_current_user),
):
    logger.debug(f'list_libraries: query={query}, page={page}, page_size={page_size}, library_type={library_type}, is_active={is_active}, is_deleted={is_deleted}, auto_import={auto_import}, only_me={only_me}')
    return await service.list_libraries(
        current_user=current_user,
        query=query,
        page=page,
        page_size=page_size,
        library_type=library_type,
        is_active=is_active,
        is_deleted=is_deleted,
        auto_import=auto_import,
        only_me=only_me,
    )

# ---- 获取库封面签名（批量） ---- #
@router.post("/covers/sign", response_model=List[str])
@router_handler(action="get_library_covers_signed")
async def get_library_covers_signed(
    request: Request,
    ids: List[str] = Body(..., description="媒体库ID列表"),
    current_user=Depends(get_current_user),
):
    """
    批量返回媒体库封面（backdrop.jpg）的 Nginx 签名 URL 列表。
    - 鉴权在服务层进行（通过 get_library）
    - 资产路径通过 FilmAssetFileOps.get_library_backdrop_path 获取
    - 使用 Nginx 分发具体文件（secure_link）
    """
    return await service.list_library_covers_signed(ids, current_user=current_user)


@router.get("/{library_id}", response_model=LibraryReadResponseSchema)
@router_handler(action="get_library")
async def get_library(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    current_user=Depends(get_current_user),
):
    return await service.get_library(library_id, current_user=current_user)

@router.get("/{library_id}/stats", response_model=Dict[str, Any])
@router_handler(action="get_library_stats")
async def get_library_stats(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    current_user=Depends(get_current_user),
):
    return await service.get_library_stats(library_id, current_user=current_user)

# ---- 上传库封面（Upload） ---- #
@router.post("/{library_id}/cover", response_model=Dict[str, Any])
@router_handler(action="upload_library_cover")
async def upload_library_cover(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    file: UploadFile = File(..., description="封面图文件（multipart/form-data: file）"),
    current_user=Depends(get_current_user),
):
    ok = await service.upload_library_cover(library_id, file, current_user=current_user)
    return {"message": "上传封面成功", "ok": ok}

# ---- 新增（Create） ---- #
@router.post("/", response_model=LibraryReadResponseSchema)
@router_handler(action="create_library")
async def create_library(
    request: Request,
    payload: LibraryCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    # 使用统一的构造函数，确保与Agent工具逻辑完全一致
    model_payload = build_library_create_payload(
        name=payload.name,
        library_type=payload.type,
        description=payload.description,
        is_public=payload.is_public,
        metadata_plugins=payload.metadata_plugins,
        subtitle_plugins=payload.subtitle_plugins,
        user_id=current_user.id,
        scan_interval=payload.scan_interval,
        auto_import=payload.auto_import,
        auto_import_scan_path=payload.auto_import_scan_path,
        supported_formats=payload.supported_formats,
    )
    return await service.create_library(model_payload, current_user=current_user)

# ---- 修改（Update） ---- #
@router.patch("/{library_id}", response_model=LibraryReadResponseSchema)
@router_handler(action="update_library")
async def update_library(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    payload: LibraryUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    patch_model = LibraryUpdate(**payload.model_dump(exclude_unset=True))
    return await service.update_library(library_id, patch_model, current_user=current_user)

@router.patch("/{library_id}/active", response_model=LibraryReadResponseSchema)
@router_handler(action="update_library_active")
async def update_library_active(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    is_active: bool = Body(..., description="是否激活"),
    current_user=Depends(get_current_user),
):
    return await service.update_library_activity(
        library_id, is_active, current_user=current_user
    )

@router.patch("/{library_id}/public", response_model=LibraryReadResponseSchema)
@router_handler(action="set_library_visibility")
async def update_library_public(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    is_public: bool = Body(..., description="是否公开"),
    current_user=Depends(get_current_user),
):
    return await service.update_library_visibility(
        library_id, is_public, current_user=current_user
    )

# ---- 删除（Delete） ---- #
@router.delete("/{library_id}", response_model=Dict[str, Any])
@router_handler(action="delete_library")
async def delete_library(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    soft_delete: bool = Query(False, description="是否软删除（仅标记删除，不删除资产）"),
    current_user=Depends(get_current_user),
):
    # 服务层返回：(Model, task-id 字典)
    deleted_model, task_ctx = await service.delete_library(
        library_id, soft_delete=soft_delete, current_user=current_user
    )
    # 统一返回格式：message / success / failed，并附带任务信息（如有）
    result: Dict[str, Any] = {
        "message": f"删除库成功: {deleted_model.name}",
        "success": 1,
        "failed": 0,
    }
    if task_ctx:
        result["tasks"] = task_ctx
    return result


# ---- 重建（Restore） ---- #
@router.post("/restore", response_model=LibraryReadResponseSchema)
@router_handler(action="restore_libraray")
async def restore_library(
    request: Request,
    library_id: str = Body(..., description="媒体库ID"),
    current_user=Depends(get_current_user),
):
    restored = await service.restore_library(
        library_id,
        current_user=current_user,
    )
    return restored

# ---- 动作（Scan/Rebuild 等） ---- #
@router.post("/{library_id}/scan", response_model=Dict[str, Any])
@router_handler(action="scan_library")
@idempotent()
async def trigger_scan(
    request: Request,
    library_id: str = Path(..., description="媒体库ID"),
    current_user=Depends(get_current_user),
):
    return await service.scan_library(library_id, current_user=current_user)

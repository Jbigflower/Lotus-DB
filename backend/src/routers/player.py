from fastapi import APIRouter, Depends, Query, Body, Request, Path
from typing import Optional, List, Dict
from src.core.dependencies import get_current_user
from src.services.users.watch_history_service import WatchHistoryService
from src.services.users.auth_service import AuthService
from src.models import WatchType, WatchHistoryUpdate
from src.routers.schemas.watch_history import (
    WatchHistoryPageResultResponseSchema,
    WatchHistoryReadResponseSchema,
    WatchHistoryUpdateRequestSchema,
    WatchStatisticsResponseSchema,
    WatchHistoryCreateRequestSchema,
    DeleteResultResponseSchema,
)
from src.core.handler import router_handler
from config.logging import get_router_logger

router = APIRouter(prefix="/api/v1/player", tags=["Player"])
service = WatchHistoryService()
logger = get_router_logger("player")


@router.get("/ping")
@router_handler(action="ping")
async def ping(request: Request):
    return {"status": "ok", "router": "Player"}


@router.get("/watch-histories", response_model=WatchHistoryPageResultResponseSchema)
@router_handler(action="list_user_watch_histories")
async def list_user_watch_histories(
    request: Request,
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页大小"),
    watch_type: Optional[WatchType] = Query(None, description="观看类型过滤"),
    completed: Optional[bool] = Query(None, description="是否完播过滤（progress_percentage>=100）"),
):
    return await service.list_user_watch_histories(
        current_user=current_user,
        watch_type=watch_type,
        completed=completed,
        page=page,
        size=size,
    )


@router.patch(
    "/watch-histories/{id}", response_model=WatchHistoryReadResponseSchema
)
@router_handler(action="update_watch_history_by_id")
async def update_watch_history_by_id(
    request: Request,
    id: str = Path(..., description="播放记录ID"),
    data: WatchHistoryUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    data = WatchHistoryUpdate(**data.model_dump(exclude_unset=True, exclude={"id"}))
    return await service.update_watch_history_by_id(
        watch_history_id=id,
        data=data,
        current_user=current_user,
    )


@router.get("/watch-histories/stats", response_model=WatchStatisticsResponseSchema)
@router_handler(action="get_watch_statistics")
async def get_watch_statistics(
    request: Request,
    current_user=Depends(get_current_user),
):
    return await service.get_watch_statistics(current_user=current_user)


@router.get(
    "/watch-histories/recent", response_model=List[WatchHistoryReadResponseSchema]
)
@router_handler(action="get_recent_records")
async def get_recent_records(
    request: Request,
    current_user=Depends(get_current_user),
    limit: Optional[int] = Query(None, ge=1, le=100, description="返回条数限制"),
):
    return await service.get_recent_watch_histories(current_user=current_user, limit=limit)


@router.get("/watch-histories/by-asset", response_model=Optional[WatchHistoryReadResponseSchema])
@router_handler(action="list_user_asset_watch_histories，兜底使用")
async def list_user_asset_watch_histories(
    request: Request,
    asset_id: str = Query(..., description="资产ID"),
    asset_type: WatchType = Query(..., description="资产类型"),
    current_user=Depends(get_current_user),
):
    return await service.list_user_asset_watch_histories(asset_id=asset_id, asset_type=asset_type, current_user=current_user)


@router.post("/watch-histories/beacon", response_model=WatchHistoryReadResponseSchema)
@router_handler(action="beacon_update")
async def beacon_update_watch_history(
    request: Request,
    token: str = Query(..., description="兜底上报使用的token"),
    data: WatchHistoryUpdateRequestSchema = Body(...),
):
    auth_service = AuthService()
    current_user = await auth_service.verify_token(token)
    watch_history_id = data.id
    update_data = data.model_dump(exclude_unset=True, exclude={"id"})
    update_data = WatchHistoryUpdate(**update_data)
    return await service.update_watch_history_by_id(
        watch_history_id=watch_history_id,
        data=update_data,
        current_user=current_user,
    )


# 新增：创建播放记录
@router.post("/watch-histories", response_model=WatchHistoryReadResponseSchema)
@router_handler(action="create_watch_history")
async def create_watch_history(
    request: Request,
    data: WatchHistoryCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    return await service.create_watch_history(payload=data, current_user=current_user)


@router.delete("/watch-histories", response_model=DeleteResultResponseSchema)
@router_handler(action="delete_watch_histories")
async def delete_watch_history(
    request: Request,
    current_user=Depends(get_current_user),
    watch_history_ids: Optional[List[str]] = Body(None, description="指定删除的观看历史ID（不传则无动作）"),
):
    deleted = await service.delete_watch_histories(
        current_user=current_user, watch_history_ids=watch_history_ids
    )
    return {"deleted": deleted, "message": "删除成功", "ok": True}

# 新增：根据播放记录ID获取详情
@router.get("/watch-histories/{id}", response_model=WatchHistoryReadResponseSchema)
@router_handler(action="get_watch_history_by_id")
async def get_watch_history_by_id(
    request: Request,
    id: str = Path(..., description="播放记录ID"),
    current_user=Depends(get_current_user),
):
    return await service.get_watch_history_by_id(watch_history_id=id, current_user=current_user)

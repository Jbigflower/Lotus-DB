# 顶部：统一引入 Request、router_handler、依赖与服务
from fastapi import APIRouter, Request, Depends, Body, Query
from src.core.handler import router_handler
from src.core.dependencies import get_current_user
from src.services.system.system_service import SystemService
from src.routers.schemas.system import (
    HealthResponseSchema,
    StatusResponseSchema,
    VersionResponseSchema,
    ConfigPatchRequestSchema,
    ConfigPatchResponseSchema,
    LogQuerySchema,
    LogFetchResponse,
    ResourceUsageResponseSchema,
    UserActivityResponseSchema,
)

router = APIRouter(prefix="/api/v1/system", tags=["System"])
service = SystemService()

@router.get("/ping")
async def ping():
    return {"status": "ok", "router": "System"}

@router.get("/health", response_model=HealthResponseSchema)
@router_handler(action="health_check")
async def health(request: Request):
    return await service.health_check()

@router.get("/status", response_model=StatusResponseSchema)
@router_handler(action="status_monitor")
async def status(request: Request):
    return await service.status_monitor()

@router.get("/version", response_model=VersionResponseSchema)
@router_handler(action="version_info")
async def version(request: Request):
    return await service.version_info()

@router.patch("/config", response_model=ConfigPatchResponseSchema)
@router_handler(action="patch_config")
async def patch_config(
    request: Request,
    data: ConfigPatchRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    return await service.patch_config(data, current_user)

@router.get("/logs", response_model=LogFetchResponse)
@router_handler(action="get_logs")
async def get_logs(
    request: Request,
    type: str = Query(..., description="日志类型"),
    lines: int = Query(100, ge=1, le=2000, description="返回的最后 N 行"),
    current_user=Depends(get_current_user),
):
    data: LogQuerySchema = LogQuerySchema(type=type, lines=lines)
    return await service.get_logs(data, current_user)

@router.get("/resources", response_model=ResourceUsageResponseSchema)
@router_handler(action="resource_usage")
async def resources(
    request: Request,
    current_user=Depends(get_current_user),
):
    return await service.resource_usage(current_user)


@router.get("/activities", response_model=UserActivityResponseSchema)
@router_handler(action="get_user_activities")
async def activities(
    request: Request,
    current_user=Depends(get_current_user),
):
    return await service.get_user_activities(current_user)

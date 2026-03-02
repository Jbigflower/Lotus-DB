from fastapi import APIRouter, Depends, Query, Path, Request
from typing import Optional
from src.core.dependencies import get_current_user
from src.services import TaskService
from src.models import (
    TaskType,
    TaskSubType,
    TaskStatus,
    TaskPriority,
    ProgressInfo,
)
from src.core.handler import router_handler
from config.logging import get_router_logger, get_trace_id
from src.routers.schemas.task import TaskReadResponseSchema, TaskPageResultResponseSchema
from src.core.idempotency import idempotent

router = APIRouter(prefix="/api/v1/tasks", tags=["Tasks"])
service = TaskService()
logger = get_router_logger("tasks")

# -------------------- Query --------------------

@router.get("/", response_model=TaskPageResultResponseSchema)
@router_handler(action="list_tasks")
async def list_tasks(
    request: Request,
    current_user=Depends(get_current_user),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页大小"),
    query: Optional[str] = Query(None, description="任务名/描述模糊搜索"),
    task_type: Optional[TaskType] = Query(None, description="任务主类型筛选"),
    sub_type: Optional[TaskSubType] = Query(None, description="任务子类型筛选"),
    status: Optional[TaskStatus] = Query(None, description="状态筛选"),
    priority: Optional[TaskPriority] = Query(None, description="优先级筛选"),
    user_id: Optional[str] = Query(None, description="按用户筛选（仅管理员）"),
):
    context = {
        "current_user": current_user,
        "trace_id": get_trace_id(),
        "request": {"path": str(request.url.path), "method": request.method},
    }
    return await service.list_tasks(
        context=context,
        page=page,
        size=size,
        query=query,
        task_type=task_type,
        sub_type=sub_type,
        status=status,
        priority=priority,
        user_id=user_id,
    )


@router.get("/{task_id}", response_model=TaskReadResponseSchema)
@router_handler(action="get_task_detail")
async def get_task_detail(
    request: Request,
    task_id: str = Path(..., description="任务ID"),
    current_user=Depends(get_current_user),
):
    context = {
        "current_user": current_user,
        "trace_id": get_trace_id(),
        "request": {"path": str(request.url.path), "method": request.method},
    }
    return await service.get_task_detail(task_id, context=context)


@router.get("/{task_id}/progress", response_model=ProgressInfo)
@router_handler(action="get_task_progress")
async def get_task_progress(
    request: Request,
    task_id: str = Path(..., description="任务ID"),
    current_user=Depends(get_current_user),
):
    context = {
        "current_user": current_user,
        "trace_id": get_trace_id(),
        "request": {"path": str(request.url.path), "method": request.method},
    }
    return await service.get_task_progress(task_id, context=context)

# -------------------- Update --------------------

@router.patch("/{task_id}/cancel", response_model=TaskReadResponseSchema)
@router_handler(action="cancel_task")
async def cancel_task(
    request: Request,
    task_id: str = Path(..., description="任务ID"),
    current_user=Depends(get_current_user),
):
    context = {
        "current_user": current_user,
        "trace_id": get_trace_id(),
        "request": {"path": str(request.url.path), "method": request.method},
    }
    return await service.cancel_task(task_id, context=context)


@router.post("/{task_id}/retry", response_model=dict)
@router_handler(action="retry_task")
@idempotent()
async def retry_task(
    request: Request,
    task_id: str = Path(..., description="任务ID"),
    current_user=Depends(get_current_user),
):
    context = {
        "current_user": current_user,
        "trace_id": get_trace_id(),
        "request": {"path": str(request.url.path), "method": request.method},
    }
    model_result, task_info = await service.retry_task(task_id, context=context)
    return {
        "data": model_result.model_dump(),
        "task": task_info,
    }


@router.delete("/{task_id}", response_model=bool)
@router_handler(action="delete_task")
async def delete_task(
    request: Request,
    task_id: str = Path(..., description="任务ID"),
    current_user=Depends(get_current_user),
):
    context = {
        "current_user": current_user,
        "trace_id": get_trace_id(),
        "request": {"path": str(request.url.path), "method": request.method},
    }
    return await service.delete_task(task_id, context=context)

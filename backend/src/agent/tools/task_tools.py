from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class ListTasksSchema(BaseModel):
    """查询任务列表参数模型。"""

    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")
    query: Optional[str] = Field(default=None, description="关键词")
    task_type: Optional[str] = Field(default=None, description="任务类型")
    sub_type: Optional[str] = Field(default=None, description="子类型")
    status: Optional[str] = Field(default=None, description="状态")
    priority: Optional[str] = Field(default=None, description="优先级")
    user_id: Optional[str] = Field(default=None, description="用户ID（管理员可指定）")


class GetTaskSchema(BaseModel):
    """获取任务详情参数模型。"""

    task_id: str = Field(description="任务ID")


class CancelTaskSchema(BaseModel):
    """取消任务参数模型。"""

    task_id: str = Field(description="任务ID")


class RetryTaskSchema(BaseModel):
    """重试任务参数模型。"""

    task_id: str = Field(description="任务ID")


class DeleteTaskSchema(BaseModel):
    """删除任务参数模型。"""

    task_id: str = Field(description="任务ID")


@dataclass
class _FallbackUser:
    id: str
    role: str = UserRole.USER


async def _get_current_user(ctx: Optional[RequestContext]) -> Optional[Any]:
    """根据上下文获取当前用户对象。"""
    if ctx is None:
        return None
    try:
        from src.logic.users.user_logic import UserLogic

        logic = UserLogic()
        return await logic.get_user(ctx.user_id)
    except Exception:
        return _FallbackUser(id=ctx.user_id, role=UserRole.USER)


def _get_task_service() -> Any:
    """获取 TaskService 实例。"""
    from src.services.tasks.task_service import TaskService

    return TaskService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def list_tasks_tool(
    page: int,
    size: int,
    query: Optional[str],
    task_type: Optional[str],
    sub_type: Optional[str],
    status: Optional[str],
    priority: Optional[str],
    user_id: Optional[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """按条件查询任务列表。"""
    validated = _validate_schema(
        ListTasksSchema,
        page=page,
        size=size,
        query=query,
        task_type=task_type,
        sub_type=sub_type,
        status=status,
        priority=priority,
        user_id=user_id,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_task_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import TaskType, TaskSubType, TaskStatus, TaskPriority

        ttype = TaskType(validated.task_type) if validated.task_type else None
        stype = TaskSubType(validated.sub_type) if validated.sub_type else None
        s = TaskStatus(validated.status) if validated.status else None
        p = TaskPriority(validated.priority) if validated.priority else None
        result = await service.list_tasks(
            context={"current_user": current_user},
            page=validated.page,
            size=validated.size,
            query=validated.query,
            task_type=ttype,
            sub_type=stype,
            status=s,
            priority=p,
            user_id=validated.user_id,
        )
        return f"任务列表: {result.model_dump()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def get_task_detail_tool(
    task_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取任务详情。"""
    if not task_id:
        return "参数验证失败: task_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_task_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        read = await service.get_task_detail(task_id, context={"current_user": current_user})
        return f"任务详情: {read.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def cancel_task_tool(
    task_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """取消指定任务。"""
    if not task_id:
        return "参数验证失败: task_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_task_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        updated = await service.cancel_task(task_id, context={"current_user": current_user})
        return f"任务已取消: {updated.model_dump()}"
    except Exception as e:
        return f"取消失败: {str(e)}"


async def get_task_progress_tool(
    task_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """查询任务进度。"""
    if not task_id:
        return "参数验证失败: task_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_task_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        progress = await service.get_task_progress(task_id, context={"current_user": current_user})
        return f"任务进度: {progress.model_dump() if hasattr(progress, 'model_dump') else progress}"
    except Exception as e:
        return f"获取失败: {str(e)}"


async def retry_task_tool(
    task_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """重试指定任务。"""
    if not task_id:
        return "参数验证失败: task_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_task_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        updated, ctx = await service.retry_task(task_id, context={"current_user": current_user})
        return f"任务已重试: {updated.model_dump()}, 上下文: {ctx}"
    except Exception as e:
        return f"重试失败: {str(e)}"


async def delete_task_tool(
    task_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """删除指定任务记录。"""
    if not task_id:
        return "参数验证失败: task_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_task_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        ok = await service.delete_task(task_id, context={"current_user": current_user})
        return f"任务删除结果: {ok}"
    except Exception as e:
        return f"删除失败: {str(e)}"


def register_task_tools(registry: ToolRegistry) -> None:
    """注册任务相关工具。"""
    registry.register(
        ToolDefinition(
            name="list_tasks",
            description="按条件查询任务列表。",
            parameters=_schema(ListTasksSchema),
            handler=list_tasks_tool,
            category="tasks",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_task_detail",
            description="获取任务详情。",
            parameters=_schema(GetTaskSchema),
            handler=get_task_detail_tool,
            category="tasks",
        )
    )
    registry.register(
        ToolDefinition(
            name="cancel_task",
            description="取消指定任务。",
            parameters=_schema(CancelTaskSchema),
            handler=cancel_task_tool,
            category="tasks",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_task_progress",
            description="查询任务进度。",
            parameters=_schema(GetTaskSchema),
            handler=get_task_progress_tool,
            category="tasks",
        )
    )
    registry.register(
        ToolDefinition(
            name="retry_task",
            description="重试指定任务。",
            parameters=_schema(RetryTaskSchema),
            handler=retry_task_tool,
            category="tasks",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_task",
            description="删除指定任务记录。",
            parameters=_schema(DeleteTaskSchema),
            handler=delete_task_tool,
            category="tasks",
            requires_confirmation=True,
        )
    )
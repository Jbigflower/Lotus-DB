from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional
from src.services.tasks.task_service import TaskService


class ListTasksSchema(BaseModel):
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")
    query: Optional[str] = Field(default=None, description="关键词")
    task_type: Optional[str] = Field(default=None, description="任务类型")
    sub_type: Optional[str] = Field(default=None, description="子类型")
    status: Optional[str] = Field(default=None, description="状态")
    priority: Optional[str] = Field(default=None, description="优先级")
    user_id: Optional[str] = Field(default=None, description="用户ID（管理员可指定）")


class GetTaskSchema(BaseModel):
    task_id: str = Field(description="任务ID")


class CancelTaskSchema(BaseModel):
    task_id: str = Field(description="任务ID")


class RetryTaskSchema(BaseModel):
    task_id: str = Field(description="任务ID")


class DeleteTaskSchema(BaseModel):
    task_id: str = Field(description="任务ID")


@tool(args_schema=ListTasksSchema)
async def list_tasks_tool(
    page: int,
    size: int,
    query: Optional[str],
    task_type: Optional[str],
    sub_type: Optional[str],
    status: Optional[str],
    priority: Optional[str],
    user_id: Optional[str],
    runtime: ToolRuntime,
) -> str:
    """按条件查询任务列表。"""
    current_user = runtime.context.get("user")
    service = TaskService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import TaskType, TaskSubType, TaskStatus, TaskPriority
        ttype = TaskType(task_type) if task_type else None
        stype = TaskSubType(sub_type) if sub_type else None
        s = TaskStatus(status) if status else None
        p = TaskPriority(priority) if priority else None
        result = await service.list_tasks(
            context={"current_user": current_user},
            page=page,
            size=size,
            query=query,
            task_type=ttype,
            sub_type=stype,
            status=s,
            priority=p,
            user_id=user_id,
        )
        return f"任务列表: {result.model_dump()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=GetTaskSchema)
async def get_task_detail_tool(
    task_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取任务详情。"""
    current_user = runtime.context.get("user")
    service = TaskService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        read = await service.get_task_detail(task_id, context={"current_user": current_user})
        return f"任务详情: {read.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=CancelTaskSchema)
async def cancel_task_tool(
    task_id: str,
    runtime: ToolRuntime,
) -> str:
    """取消指定任务。"""
    current_user = runtime.context.get("user")
    service = TaskService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        updated = await service.cancel_task(task_id, context={"current_user": current_user})
        return f"任务已取消: {updated.model_dump()}"
    except Exception as e:
        return f"取消失败: {str(e)}"


@tool(args_schema=GetTaskSchema)
async def get_task_progress_tool(
    task_id: str,
    runtime: ToolRuntime,
) -> str:
    """查询任务进度。"""
    current_user = runtime.context.get("user")
    service = TaskService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        progress = await service.get_task_progress(task_id, context={"current_user": current_user})
        return f"任务进度: {progress.model_dump() if hasattr(progress, 'model_dump') else progress}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=RetryTaskSchema)
async def retry_task_tool(
    task_id: str,
    runtime: ToolRuntime,
) -> str:
    """重试指定任务。"""
    current_user = runtime.context.get("user")
    service = TaskService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        updated, ctx = await service.retry_task(task_id, context={"current_user": current_user})
        return f"任务已重试: {updated.model_dump()}, 上下文: {ctx}"
    except Exception as e:
        return f"重试失败: {str(e)}"


@tool(args_schema=DeleteTaskSchema)
async def delete_task_tool(
    task_id: str,
    runtime: ToolRuntime,
) -> str:
    """删除指定任务记录。"""
    current_user = runtime.context.get("user")
    service = TaskService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        ok = await service.delete_task(task_id, context={"current_user": current_user})
        return f"任务删除结果: {ok}"
    except Exception as e:
        return f"删除失败: {str(e)}"

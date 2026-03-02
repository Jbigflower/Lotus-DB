from typing import Optional, Dict, Any
from src.logic import TaskLogic
from src.models import (
    TaskType,
    TaskSubType,
    TaskStatus,
    TaskPriority,
    TaskRead,
    TaskPageResult,
    ProgressInfo,
    UserRole,
)
from src.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from src.core.handler import service_handler
from config.logging import get_service_logger
from src.async_worker.core import send_task


class TaskService:
    def __init__(self):
        self.logic = TaskLogic()
        self.logger = get_service_logger("tasks")

    def _ensure_list_permission(self, current_user, user_id: Optional[str]) -> Optional[str]:
        # 管理员可以查看任意用户；未提供 user_id 则不过滤
        if getattr(current_user, "role", "USER") == UserRole.ADMIN:
            return user_id
        # 非管理员禁止查看其他用户
        if user_id and user_id != current_user.id:
            raise ForbiddenError("无权限查看其他用户的任务")
        # 非管理员缺省仅查看本人
        return current_user.id

    @service_handler(action="list_tasks")
    async def list_tasks(
        self,
        *,
        context: Dict[str, Any],
        page: int = 1,
        size: int = 20,
        query: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        sub_type: Optional[TaskSubType] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        user_id: Optional[str] = None,
    ) -> TaskPageResult:
        current_user = context.get("current_user")
        uid_filter = self._ensure_list_permission(current_user, user_id)
        return await self.logic.search_tasks(
            query=query,
            task_type=task_type,
            sub_type=sub_type,
            status=status,
            priority=priority,
            user_id=uid_filter,
            page=page,
            page_size=size,
        )

    @service_handler(action="get_task_detail")
    async def get_task_detail(self, task_id: str, *, context: Dict[str, Any]) -> TaskRead:
        current_user = context.get("current_user")
        task = await self.logic.get_task(task_id)
        if (
            getattr(current_user, "role", "USER") != "ADMIN"
            and task.user_id
            and (task.user_id != current_user.id)
        ):
            raise ForbiddenError("无权限查看该任务")
        return task

    @service_handler(action="cancel_task")
    async def cancel_task(self, task_id: str, *, context: Dict[str, Any]) -> TaskRead:
        current_user = context.get("current_user")
        task = await self.logic.get_task(task_id)
        if (
            getattr(current_user, "role", "USER") != "ADMIN"
            and task.user_id
            and (task.user_id != current_user.id)
        ):
            raise ForbiddenError("无权限取消该任务")
        # 允许取消 PAUSED（与 Logic 的合法状态转移一致）
        if task.status not in [
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.RETRYING,
            TaskStatus.PAUSED,
        ]:
            raise ValidationError("只能取消待处理、运行中、重试中的或暂停的任务")
        updated = await self.logic.cancel_task(task_id)
        return updated

    @service_handler(action="get_task_progress")
    async def get_task_progress(self, task_id: str, *, context: Dict[str, Any]) -> ProgressInfo:
        current_user = context.get("current_user")
        task = await self.logic.get_task(task_id)
        if (
            getattr(current_user, "role", "USER") != "ADMIN"
            and task.user_id
            and (task.user_id != current_user.id)
        ):
            raise ForbiddenError("无权限查看该任务进度")
        return await self.logic.get_task_progress(task_id)

    @service_handler(action="retry_task")
    async def retry_task(self, task_id: str, *, context: Dict[str, Any]) -> tuple[TaskRead, Dict[str, Any]]:
        current_user = context.get("current_user")
        task = await self.logic.get_task(task_id)
        if (
            getattr(current_user, "role", "USER") != "ADMIN"
            and task.user_id
            and (task.user_id != current_user.id)
        ):
            raise ForbiddenError("无权限重试该任务")

        updated = await self.logic.retry_task(task_id)
        worker_name = updated.sub_type.value  # 使用枚举的 .value 作为 worker 名称

        payload = dict(updated.parameters or {})
        payload["task_id"] = task_id
        msg_id = await send_task(
            worker_name,
            payload=payload,
            priority=updated.priority,
            max_retries=updated.max_retries,
        )

        final = await self.logic.mark_retry_running(task_id)
        return final, {"task_id": msg_id, "task_name": worker_name}

    @service_handler(action="delete_task")
    async def delete_task(self, task_id: str, *, context: Dict[str, Any]) -> bool:
        current_user = context.get("current_user")
        task = await self.logic.get_task(task_id)
        if (
            getattr(current_user, "role", "USER") != "ADMIN"
            and task.user_id
            and (task.user_id != current_user.id)
        ):
            raise ForbiddenError("无权限删除该任务")
        
        return await self.logic.delete_task(task_id)

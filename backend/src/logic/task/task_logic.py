from datetime import datetime, timezone
from typing import Optional, Dict, Any
from bson import ObjectId
from pymongo import ReturnDocument
from src.repos.mongo_repos.task.task_repo import TaskRepo
from src.models import (
    TaskCreate,
    TaskInDB,
    TaskRead,
    TaskUpdate,
    TaskStatus,
    TaskType,
    TaskSubType,
    TaskPageResult,
    TaskPriority,
)
from src.logic.base_logic import BaseLogic
from src.core.exceptions import NotFoundError, ValidationError
from src.repos.cache_repos.task_redis_repo import TaskRedisRepo
from config.logging import get_logic_logger
from src.core.handler import logic_handler


class TaskLogic(BaseLogic[TaskInDB, TaskCreate, TaskUpdate, TaskRead]):

    VALID_TRANSITIONS = {
        TaskStatus.PENDING: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
        TaskStatus.RUNNING: [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.PAUSED],
        TaskStatus.PAUSED: [TaskStatus.RUNNING, TaskStatus.CANCELLED],
        TaskStatus.FAILED: [TaskStatus.RETRYING],
        TaskStatus.RETRYING: [TaskStatus.RUNNING],
    }

    def __init__(self):
        super().__init__(
            repo=TaskRepo(),
            read_model=TaskRead,
            cache_repo=TaskRedisRepo(),
        )
        self.logger = get_logic_logger("task_logic")

    # def __getattribute__(self, name):
    #     attr = super().__getattribute__(name)

    #     # 允许访问普通属性或私有变量
    #     if not callable(attr) or name.startswith("_"):
    #         return attr

    #     # 获取当前类定义的方法集合
    #     cls = type(self)
    #     current_methods = cls.__dict__.keys()

    #     # 若该方法不是当前类自己定义的（来自父类），禁止访问
    #     if name not in current_methods:
    #         raise AttributeError(f"禁止直接调用父类方法 '{name}'，请使用 LibraryLogic 提供的封装接口")

    #     return attr

    # ----------------------------- 选用的父类方法 -----------------------------

    @logic_handler("获取任务详情")
    async def get_task(self, task_id: str, session=None) -> TaskRead:
        result = await super().get_by_id(task_id, session=session)
        return result

    @logic_handler("创建任务")
    async def create_task(
        self, payload: TaskCreate, session=None
    ) -> TaskRead:
        created = await super().create(payload, session=session)
        return created

    @logic_handler("更新任务")
    async def update_task(
        self, task_id: str, task_update: TaskUpdate, session=None
    ) -> TaskRead:
        updated = await super().update_by_id(task_id, task_update, session=session)
        return updated

    @logic_handler("删除任务")
    async def delete_task(self, task_id: str, session=None) -> bool:
        count = await super().delete_by_id(task_id, soft_delete=False, session=session)
        return count > 0


    # ----------------------------- 子类特有方法 -----------------------------
    # ----------------------------- 任务状态更新 (CAS原子化) -----------------------------
    async def transition_task_status(
        self,
        task_id: str,
        expected_status: TaskStatus,
        new_status: TaskStatus,
        update_data: Optional[Dict[str, Any]] = None,
        session=None,
    ) -> TaskRead:
        """
        原子化更新任务状态 (CAS)
        :param task_id: 任务ID
        :param expected_status: 期望的当前状态 (用于CAS校验)
        :param new_status: 目标状态
        :param update_data: 其他需要更新的字段
        :return: 更新后的任务对象
        """
        if not update_data:
            update_data = {}
        
        now = datetime.now(timezone.utc)
        
        # 准备更新字段
        set_fields = {
            "status": new_status.value,
            "updated_at": now,
            **update_data
        }
        
        if new_status == TaskStatus.RUNNING:
            set_fields["started_at"] = now
        elif new_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            set_fields["completed_at"] = now
            
        # CAS 原子更新: status == expected_status
        updated_doc = await self.repo.collection.find_one_and_update(
            {"_id": ObjectId(task_id), "status": expected_status.value},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
            session=session
        )
        
        if not updated_doc:
            # 检查任务是否存在
            task = await self.repo.find_by_id(task_id, session=session)
            if not task:
                raise NotFoundError(f"任务不存在: {task_id}")
            
            # 如果状态已经是目标状态，视为幂等成功，直接返回
            if task.status == new_status.value:
                return self.read_model(**task.model_dump())
            
            # 状态不匹配且不是目标状态，抛出异常
            raise ValidationError(f"任务状态不匹配: 期望 {expected_status.value}, 实际 {task.status}")
            
        return self.read_model(**self.repo.convert_dict_to_pydanticModel([updated_doc])[0].model_dump())

    # ----------------------------- 任务启动 ｜ 暂停 -----------------------------
    async def start_task(self, task_id: str, session=None) -> TaskRead:
        return await self.transition_task_status(
            task_id, 
            expected_status=TaskStatus.PENDING, 
            new_status=TaskStatus.RUNNING, 
            session=session
        )

    async def cancel_task(self, task_id: str, session=None) -> TaskRead:
        task = await self.get_task(task_id, session=session)
        try:
            current_status = TaskStatus(task.status)
        except ValueError:
            # Handle case where status might be invalid
            raise ValidationError(f"Invalid task status: {task.status}")

        if current_status in (TaskStatus.RUNNING, TaskStatus.RETRYING):
            # 先暂停
            await self.transition_task_status(
                task_id, 
                expected_status=current_status, 
                new_status=TaskStatus.PAUSED, 
                session=session
            )
            # 再取消
            return await self.transition_task_status(
                task_id, 
                expected_status=TaskStatus.PAUSED, 
                new_status=TaskStatus.CANCELLED, 
                session=session
            )
        elif current_status in (TaskStatus.PENDING, TaskStatus.PAUSED):
            return await self.transition_task_status(
                task_id, 
                expected_status=current_status, 
                new_status=TaskStatus.CANCELLED, 
                session=session
            )
        else:
            if current_status == TaskStatus.CANCELLED:
                return task
            raise ValidationError(f"任务 {task_id} 当前状态不允许取消: {task.status}")

    async def retry_task(self, task_id: str, session=None) -> TaskRead:
        """重试失败任务"""
        task = await self.get_task(task_id, session=session)
        if not task:
            raise NotFoundError(f"任务不存在: {task_id}")
        
        if task.status != TaskStatus.FAILED.value:
            raise ValidationError(f"只有失败的任务才能重试，当前: {task.status}")
        
        if task.retry_count >= task.max_retries:
            raise ValidationError(f"任务已达到最大重试次数: {task.retry_count}/{task.max_retries}")

        return await self.transition_task_status(
            task_id,
            expected_status=TaskStatus.FAILED,
            new_status=TaskStatus.RETRYING,
            session=session
        )

    async def mark_retry_running(self, task_id: str, session=None) -> TaskRead:
        """从 RETRYING 切换到 RUNNING"""
        return await self.transition_task_status(
            task_id, 
            expected_status=TaskStatus.RETRYING, 
            new_status=TaskStatus.RUNNING, 
            session=session
        )

    async def complete_task(self, task_id: str, result: Dict[str, Any], session=None) -> TaskRead:
        """完成任务"""
        return await self.transition_task_status(
            task_id, 
            expected_status=TaskStatus.RUNNING, 
            new_status=TaskStatus.COMPLETED, 
            update_data={"result": result},
            session=session
        )

    async def fail_task(
        self,
        task_id: str,
        error_message: str,
        error_details: Dict[str, Any] = None,
        session=None,
    ) -> TaskRead:
        """失败任务"""
        update_data = {"error_message": error_message}
        if error_details:
            update_data["error_details"] = error_details
            
        return await self.transition_task_status(
            task_id, 
            expected_status=TaskStatus.RUNNING, 
            new_status=TaskStatus.FAILED, 
            update_data=update_data,
            session=session
        )

    # -------------------------- search Bar -----------------------------
    async def search_tasks(
        self,
        query: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        sub_type: Optional[TaskSubType] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        user_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        session=None,
    ) -> TaskPageResult:
        """搜索任务（迁移自 Repo.search_tasks）"""
        params = {k: v for k, v in locals().items() if k not in ("self", "session")}
        search_key = self._build_search_key(**params)
        cached = await self.cache_repo.get_search_page(search_key, page)
        if cached:
            return TaskPageResult(**cached)
        
        filter_dict: Dict[str, Any] = {}
        if query:
            text_fields = ["name", "description", "root_path"]
            filter_dict["$or"] = [{f: {"$regex": query, "$options": "i"}} for f in text_fields]
        if task_type:
            filter_dict["type"] = task_type.value
        if user_id is not None:
            filter_dict["user_id"] = ObjectId(user_id)
        if status is not None:
            filter_dict["status"] = status.value
        if priority is not None:
            filter_dict["priority"] = priority.value
        if sub_type:
            filter_dict["sub_type"] = sub_type.value

        skip = max(page - 1, 0) * page_size
        results = await self.repo.find(
            filter_dict,
            skip=skip,
            limit=page_size,
            session=session,
        )
        total = await self.repo.count(filter_dict, session=session)
        pages = (total + page_size - 1) // page_size

        page_result = TaskPageResult(
            items=results, total=total, page=page, size=page_size, pages=pages
        )
        await self.cache_repo.cache_search_page(search_key, page, page_result.model_dump())
        return page_result
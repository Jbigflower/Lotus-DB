from typing import List, Optional, Union
from pydantic import BaseModel, Field
from src.models import TaskCreate, TaskRead, TaskPageResult, TaskUpdate


class TaskCreateRequestSchema(TaskCreate):
    """创建任务请求模型"""

    user_id: Optional[str] = Field(
        None, description="用户ID，由依赖注入完成，前端无需传递"
    )


class TaskUpdateRequestSchema(TaskUpdate):
    """更新任务请求模型"""

    pass  # 所有字段从 TaskUpdate 继承


class TaskReadResponseSchema(TaskRead):
    """读取任务响应模型"""

    pass  # 所有字段从 TaskRead 继承，Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return TaskRead


class TaskPageResultResponseSchema(TaskPageResult):
    """任务分页结果响应模型"""

    pass

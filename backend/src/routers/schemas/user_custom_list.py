from typing import List, Optional, Union
from pydantic import BaseModel, Field
from src.models import (
    CustomListCreate,
    CustomListUpdate,
    CustomListRead,
    CustomListPageResult,
)


class CustomListCreateRequestSchema(CustomListCreate):
    """创建自定义片单请求模型"""

    user_id: Optional[str] = Field(None, description="用户ID，后端依赖注入获取")


class CustomListUpdateRequestSchema(CustomListUpdate):
    """更新自定义片单请求模型"""

    pass  # 所有字段从 CustomListUpdate 继承


class CustomListReadResponseSchema(CustomListRead):
    """读取自定义片单响应模型"""

    pass  # 所有字段从 CustomListRead 继承，Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return CustomListRead


class CustomListPageResultResponseSchema(CustomListPageResult):
    """自定义片单分页结果响应模型"""

    pass


class AddMoviesSchema(BaseModel):
    movie_ids: List[str] = Field(..., description="影片ID列表，非空")


class RemovieMoviesSchema(BaseModel):
    movie_ids: List[str] = Field(..., description="影片ID列表，非空")
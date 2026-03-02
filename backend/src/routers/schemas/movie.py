from typing import List, Optional
from pydantic import BaseModel, Field
from src.models import MovieCreate, MovieUpdate, MovieRead


class MovieCreateRequestSchema(MovieCreate):
    """创建电影请求模型"""
    pass


class MovieUpdateRequestSchema(MovieUpdate):
    """更新电影请求模型"""

    pass  # 所有字段从 MovieUpdate 继承


class MovieReadResponseSchema(MovieRead):
    is_favoriter: Optional[bool] = Field(None, description="当前用户是否收藏了该影片")
    is_watchLater: Optional[bool] = Field(None, description="当前用户是否加入了稍后观看")


class MoviePageResultResponseSchema(BaseModel):
    items: List[MovieReadResponseSchema] = Field(default_factory=list, description="电影列表")
    total: int = Field(0, description="总数量")
    page: int = Field(1, description="当前页码")
    size: int = Field(20, description="每页大小")
    pages: int = Field(0, description="总页数")

# 新增：批量更新请求模型
class MovieBatchUpdateRequestSchema(BaseModel):
    movie_ids: List[str] = Field(..., description="影片ID列表")
    patch: MovieUpdateRequestSchema = Field(..., description="更新内容")


class MovieCreateResponseSchema(BaseModel):
    movie_info: MovieReadResponseSchema = Field(..., description="创建的电影信息")
    task_id: str = Field(..., description="异步任务ID")

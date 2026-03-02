from typing import List, Optional, Union
from pydantic import BaseModel, Field
from src.models import LibraryCreate, LibraryUpdate, LibraryPageResult, LibraryRead


class LibraryCreateRequestSchema(LibraryCreate):
    """创建库请求模型"""

    user_id: Optional[str] = Field(
        None, description="用户ID，由依赖注入完成，前端无需传递"
    )
    root_path: Optional[str] = Field(
        None, description="媒体库路径，系统根据其他字段自动拼接，无需传递"
    )
    # 新增：前端按类型选择插件（两个下拉列表）
    metadata_plugins: Optional[List[str]] = Field(
        None, description="启用的元数据类插件（如 tmdb/omdb）"
    )
    subtitle_plugins: Optional[List[str]] = Field(
        None, description="启用的字幕类插件（如 opensubtitles）"
    )


class LibraryUpdateRequestSchema(LibraryUpdate):
    """更新库请求模型"""

    pass  # 所有字段从 LibraryUpdate 继承


class LibraryReadResponseSchema(LibraryRead):
    """读取库响应模型"""

    pass  # 所有字段从 LibraryRead 继承，Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return LibraryRead


class LibraryPageResultResponseSchema(LibraryPageResult):
    """库分页结果响应模型"""

    pass

from typing import List, Optional, Union
from pydantic import BaseModel, Field
from src.models import AssetCreate, AssetUpdate, AssetRead, AssetPageResult, AssetStoreType


class AssetCreateRequestSchema(AssetCreate):
    """创建资产请求模型"""

    # 排除 path 和 library_id 字段
    path: Optional[str] = Field(None, description="文件路径", exclude=True)
    library_id: Optional[str] = Field(None, description="库ID", exclude=True)
    store_type: Optional[AssetStoreType] = Field(AssetStoreType.LOCAL, description="存储类型")

class AssetUpdateRequestSchema(AssetUpdate):
    """更新资产请求模型"""

    pass  # 所有字段从 AssetUpdate 继承


class AssetReadResponseSchema(AssetRead):
    """读取资产响应模型"""

    pass  # 所有字段从 AssetRead 继承，Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return AssetRead


class AssetPageResultResponseSchema(AssetPageResult):
    """资产分页结果响应模型"""

    pass

# 新增：批量更新请求模型
class AssetBatchUpdateRequestSchema(BaseModel):
    asset_ids: List[str] = Field(..., description="资产ID列表")
    patch: AssetUpdateRequestSchema = Field(..., description="更新内容")

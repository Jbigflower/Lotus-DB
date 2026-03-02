from typing import List, Optional, Union, Dict, Tuple
from pydantic import BaseModel, Field
from src.models import (
    PartialPageResult,
    UserAssetType,
    AssetStoreType,
    UserAssetBase,
    UserAssetCreate,
    UserAssetUpdate,
    UserAssetRead,
    UserAssetPageResult,
)


class UserAssetCreateRequestSchema(UserAssetCreate):
    """创建用户资产请求模型（路由层）"""

    # 路由/服务层会自动注入 user_id，前端不要传
    user_id: Optional[str] = Field(None, description="所属用户ID，由依赖注入完成")
    store_type: Optional[AssetStoreType] = Field(None, description="资产存储类型（未提供时由路由/服务层默认填充为 local")
    # 上传/导入场景下由系统自动生成或填充
    name: Optional[str] = Field(None, description="资产名称，上传/导入时由系统生成")
    path: Optional[str] = Field(None, description="逻辑存储路径，上传/导入时由系统生成")
    actual_path: Optional[str] = Field(
        None, description="实际存储路径，上传/导入时由系统生成"
    )


class UserAssetUpdateRequestSchema(UserAssetUpdate):
    """更新用户资产请求模型（路由层）"""

    pass  # 所有字段从 UserAssetUpdate 继承


class UserAssetReadResponseSchema(UserAssetRead):
    """读取用户资产响应模型（路由层）"""

    pass  # Pydantic 模型之间的兼容性机制 + FastAPI 的自动响应序列化机制，可直接 return UserAssetRead


class UserAssetPageResultResponseSchema(UserAssetPageResult):
    """用户资产分页结果响应模型（路由层）"""

    pass


# -----------------------------
# 列表查询（与 AssetService.list_assets 对齐）
# -----------------------------
class UserAssetListQuerySchema(BaseModel):
    """用户资产列表查询参数（支持复杂筛选与分页）"""

    query: Optional[str] = Field(None, description="模糊搜索关键字")
    user_id: Optional[str] = Field(
        None, description="按用户ID筛选；普通用户可省略自动使用自身ID"
    )
    movie_id: Optional[str] = Field(None, description="按电影ID筛选")
    asset_type: Optional[List[UserAssetType]] = Field(
        None, description="按资产类型列表筛选"
    )
    tags: Optional[List[str]] = Field(None, description="标签筛选")
    is_public: Optional[bool] = Field(None, description="公开状态筛选")
    page: int = Field(1, ge=1, description="页码")
    size: int = Field(20, ge=1, le=200, description="每页数量")
    sort: Optional[List[Tuple[str, int]]] = Field(
        None, description="排序字段及方向，例如 [('created_at', -1)]"
    )
    projection: Optional[Dict[str, int]] = Field(
        None, description="投影字段，形如 {'id': 1, 'name': 1}，返回 PartialPageResult"
    )


# FastAPI 对 Union 响应模型支持有限，通常以 dict 或具体模型返回。
# 这里提供类型别名以便代码提示使用，与 AssetService.list_assets 的返回类型一致。
UserAssetListResponseUnion = Union[PartialPageResult, UserAssetPageResult]


# -----------------------------
# 批量获取 / 批量删除 / 批量更新
# -----------------------------
class UserAssetIdsRequestSchema(BaseModel):
    """通用：批量资产ID请求体"""

    asset_ids: List[str] = Field(..., min_length=1, description="资产ID列表")


class UserAssetBatchUpdateRequestSchema(BaseModel):
    """批量更新用户资产请求体"""

    asset_ids: List[str] = Field(..., min_length=1, description="待更新的资产ID列表")
    patch: UserAssetUpdateRequestSchema = Field(..., description="更新内容")


# -----------------------------
# 设置公开状态
# -----------------------------
class UserAssetSetActiveStatusRequestSchema(BaseModel):
    """批量设置资产公开状态请求体"""

    asset_ids: List[str] = Field(..., min_length=1, description="资产ID列表")
    is_public: bool = Field(..., description="是否公开")


# -----------------------------
# 资产孤立列表（无请求体）
# 返回：List[UserAssetRead]
# -----------------------------


# -----------------------------
# 资产分配
# -----------------------------
class UserAssetAllocateRequestSchema(BaseModel):
    """批量分配资产到电影请求体"""

    allocate_map: Dict[str, List[str]] = Field(
        ...,
        description="资产ID到电影ID列表的映射，如 {'asset_id': ['movie_id1','movie_id2']}",
    )


# -----------------------------
# 生成截图请求体
# -----------------------------
class ScreenshotCreateRequestSchema(BaseModel):
    """从电影资产生成用户截图的请求体"""

    asset_id: str = Field(..., description="电影资产ID（视频）")
    movie_id: str = Field(..., description="关联电影ID")
    time: float = Field(..., ge=0, description="截图时间点（秒）")
    name: Optional[str] = Field(None, description="截图名称（可选）")
    is_public: Optional[bool] = Field(False, description="是否公开")
    tags: Optional[List[str]] = Field(None, description="标签")

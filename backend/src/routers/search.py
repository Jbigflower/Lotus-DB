import asyncio
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, Query, Request, Body
from pydantic import BaseModel, Field

from src.core.dependencies import get_current_user
from src.core.handler import router_handler
from config.logging import get_router_logger

from src.services import SearchService

router = APIRouter(prefix="/api/v1/search", tags=["Search"])

logger = get_router_logger("search")

search_service = SearchService()


class NSSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索关键词")
    page: int = Field(1, ge=1, description="页码")
    size: int = Field(20, ge=1, le=200, description="每页数量")
    only_me: bool = Field(False, description="是否只返回我的资源")
    types: Optional[List[str]] = Field(
        None, description="搜索类型: movies, notes, subtitles"
    )
    top_k: Optional[int] = Field(None, ge=1, le=500, description="向量召回数量")
    vector_weight: float = Field(0.7, ge=0, le=1, description="向量分权重")
    keyword_weight: float = Field(0.3, ge=0, le=1, description="关键词分权重")
    max_per_parent: int = Field(2, ge=0, le=10, description="同一资产最大片段数")
    use_cache: bool = Field(False, description="是否启用缓存")


@router.get("/", response_model=dict)
@router_handler(action="global_search")
async def global_search(
    request: Request,
    q: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=200, description="每页数量"),
    only_me: bool = Query(False, description="是否只返回我的资源"),
    type: str = Query("summary", description="搜索类型: summary, movies, libraries, user_assets, collections, movie_assets"),
    current_user=Depends(get_current_user),
):
    """
    全局搜索资源
    """
    return await search_service.search(
        q=q,
        page=page,
        size=size,
        only_me=only_me,
        type=type,
        current_user=current_user,
    )


@router.post("/ns", response_model=dict)
@router_handler(action="ns_search")
async def ns_search(
    request: Request,
    payload: NSSearchRequest = Body(...),
    current_user=Depends(get_current_user),
):
    return await search_service.ns_search(
        query=payload.query,
        page=payload.page,
        size=payload.size,
        only_me=payload.only_me,
        types=payload.types,
        top_k=payload.top_k,
        vector_weight=payload.vector_weight,
        keyword_weight=payload.keyword_weight,
        max_per_parent=payload.max_per_parent,
        use_cache=payload.use_cache,
        current_user=current_user,
    )

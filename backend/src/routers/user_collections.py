# 顶层模块（imports 与 router 定义）
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Body, Request
from typing import List, Optional
from pydantic import BaseModel, Field, constr
from src.models import (
    CustomListUpdate,
    CustomListCreate,
    CustomListInDB,
    CustomListPageResult,
    CustomListRead,
    CustomListType,
    MovieRead,
)
from src.routers.schemas.movie import MovieReadResponseSchema
from src.routers.schemas.user_custom_list import (
    CustomListCreateRequestSchema,
    CustomListUpdateRequestSchema,
    CustomListReadResponseSchema,
    CustomListPageResultResponseSchema,
    AddMoviesSchema, RemovieMoviesSchema,
)
from src.services import CollectionService
from src.core.dependencies import get_current_user  # 返回当前登录用户对象
from src.core.handler import router_handler
from config.logging import get_router_logger, set_trace_id, get_trace_id

router = APIRouter(prefix="/api/v1/user_collections", tags=["User_Collections"])
service = CollectionService()
logger = get_router_logger("user_collections")


# -----------------------------
# 路由层实现
# -----------------------------
@router.get("/", response_model=CustomListPageResultResponseSchema)
@router_handler(action="list_collections")
async def get_user_collections(
    request: Request,
    current_user=Depends(get_current_user),
    type: Optional[CustomListType] = Query(
        None, description="可选合集类型筛选: favorite, watchlist, custom"
    ),
    query: Optional[str] = Query(None, description="关键词模糊搜索"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=200, description="每页数量"),
):
    return await service.list_collections(
        current_user.id,
        type_filter=type,
        query=query,
        page=page,
        page_size=size,
        current_user=current_user,
    )


@router.get("/{collection_id}", response_model=CustomListReadResponseSchema)
@router_handler(action="get_collection_detail")
async def get_collection_detail(
    request: Request,
    collection_id: str = Path(..., description="合集ID"),
    current_user=Depends(get_current_user),
):
    collection = await service.get_collection(collection_id, current_user=current_user)
    if not collection:
        raise HTTPException(status_code=404, detail="合集不存在或无权限访问")
    return collection


@router.post("/", response_model=CustomListReadResponseSchema)
@router_handler(action="create_collection")
async def create_collection(
    request: Request,
    data: CustomListCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    if data.type not in CustomListType.__members__.values():
        raise HTTPException(status_code=400, detail="非法合集类型")
    return await service.create_collection(data, current_user=current_user)

@router.post("/initUserDefaultCollections", response_model=List[CustomListReadResponseSchema])
@router_handler(action="create_collection")
async def create_collection(
    request: Request,
    current_user=Depends(get_current_user),
):
    return await service.init_user_default_collections(current_user=current_user)

@router.patch("/{collection_id}", response_model=CustomListReadResponseSchema)
@router_handler(action="update_collection")
async def update_collection(
    request: Request,
    collection_id: str = Path(..., description="合集ID"),
    data: CustomListUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    if data.type is not None and data.type not in CustomListType.__members__.values():
        raise HTTPException(status_code=400, detail="非法合集类型")
    return await service.update_collection(
        collection_id, data, current_user=current_user
    )


@router.delete("/{collection_id}", response_model=CustomListReadResponseSchema)
@router_handler(action="delete_collection")
async def delete_collection(
    request: Request,
    collection_id: str = Path(..., description="合集ID"),
    current_user=Depends(get_current_user),
):
    deleted = await service.delete_collection(collection_id, current_user=current_user)
    if not deleted:
        raise HTTPException(status_code=404, detail="合集不存在或已删除")
    return deleted


@router.post("/{collection_id}/add_movies", response_model=dict)
@router_handler(action="add_movies_to_collection")
async def add_movies_to_collection(
    request: Request,
    collection_id: str = Path(..., description="合集ID"),
    data: AddMoviesSchema = Body(...),
    current_user=Depends(get_current_user),
):
    if not data.movie_ids:
        raise HTTPException(status_code=400, detail="影片ID列表不能为空")
    return await service.add_movies(
        collection_id, data.movie_ids, current_user=current_user
    )


@router.post("/{collection_id}/remove_movies", response_model=dict)
@router_handler(action="remove_movies_from_collection")
async def remove_movies_from_collection(
    request: Request,
    collection_id: str = Path(..., description="合集ID"),
    data: RemovieMoviesSchema = Body(...),
    current_user=Depends(get_current_user),
):
    if not data.movie_ids:
        raise HTTPException(status_code=400, detail="影片ID列表不能为空")
    return await service.remove_movies(
        collection_id, data.movie_ids, current_user=current_user
    )

@router.get("/{collection_id}/movies", response_model=List[MovieReadResponseSchema])
@router_handler(action="get_collection_movies")
async def get_collection_movies(
    request: Request,
    collection_id: str = Path(..., description="合集ID"),
    current_user=Depends(get_current_user),
):
    movies = await service.get_collection_movies(collection_id, current_user=current_user)
    return movies

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Query,
    Path,
    Body,
    UploadFile,
    File,
    Form,
    HTTPException,
)
from typing import List, Optional, Dict, Any, Union


from src.core.dependencies import get_current_user
from src.models import AssetType, MovieCreate, MovieUpdate
from src.services import MovieService
from src.core.handler import router_handler
from config.logging import get_router_logger
from src.routers.schemas.movie import (
    MovieCreateRequestSchema,
    MovieUpdateRequestSchema,
    MovieReadResponseSchema,
    MoviePageResultResponseSchema,
    MovieBatchUpdateRequestSchema,
    MovieCreateResponseSchema,
)
from src.routers.schemas.task import TaskReadResponseSchema
from src.core.exceptions import NotFoundError
from src.core.idempotency import idempotent


router = APIRouter(prefix="/api/v1/movies", tags=["Movies"])
movie_service = MovieService()
logger = get_router_logger("movies")

# 查找
@router.get("/", response_model=MoviePageResultResponseSchema)
@router_handler(action="list_movies")
async def list_movies(
    request: Request,
    query: Optional[str] = Query(None, description="搜索关键词"),
    genres: Optional[List[str]] = Query(None, description="类型筛选"),
    min_rating: Optional[float] = Query(None, ge=0, le=10),
    max_rating: Optional[float] = Query(None, ge=0, le=10),
    start_date: Optional[str] = Query(None, description="上映日期起 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="上映日期止 YYYY-MM-DD"),
    tags: Optional[List[str]] = Query(None, description="标签筛选"),
    is_deleted: Optional[bool] = Query(None, description="是否查询已删除影片"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    sort_by: Optional[str] = Query(None, description="排序字段，如 rating, release_date, created_at"),
    sort_dir: Optional[int] = Query(None, description="排序方向：1升序，-1降序"),
    current_user=Depends(get_current_user),
    library_id: Optional[str] = Query(None, description="媒体库ID；不传表示汇总用户所有可访问库"),
):
    return await movie_service.list_movies(
        query=query,
        genres=genres,
        min_rating=min_rating,
        max_rating=max_rating,
        start_date=start_date,
        end_date=end_date,
        tags=tags,
        is_deleted=is_deleted,
        page=page,
        size=size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        current_user=current_user,
        library_id=library_id,
    )

@router.get("/recent", response_model=List[MovieReadResponseSchema])
@router_handler(action="list_recent_movies")
async def list_recent_movies(
    request: Request,
    library_id: Optional[str] = Query(None, description="媒体库ID；不传表示汇总用户所有可访问库"),
    size: int = Query(20, ge=1, le=200, description="返回数量"),
    current_user=Depends(get_current_user),
):
    return await movie_service.list_recent_movies(
        library_id=library_id,
        size=size,
        current_user=current_user,
    )

@router.get("/recycle-bin", response_model=MoviePageResultResponseSchema)
@router_handler(action="list_recycle_bin_movies")
async def list_recycle_bin_movies(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current_user=Depends(get_current_user),
):
    return await movie_service.list_recycle_bin_movies(
        page=page,
        size=size,
        current_user=current_user,
    )

# 获取单个电影详情
@router.get("/{movie_id}", response_model=MovieReadResponseSchema)
@router_handler(action="get_movie")
async def get_movie(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    current_user=Depends(get_current_user),
):
    return await movie_service.get_movie(
        movie_id, current_user=current_user
    )

# ---- 获取电影海报/缩略图/背景图签名（批量） ---- #
@router.post("/covers/sign", response_model=List[str])
@router_handler(action="get_movie_covers_signed")
async def get_movie_covers_signed(
    request: Request,
    ids: List[str] = Body(..., description="影片ID列表"),
    image: str = Body("poster.jpg", description="图片类型：poster.jpg | thumbnail.jpg | backdrop.jpg | all"),
    current_user=Depends(get_current_user),
):
    """
    批量返回电影图片（poster/thumbnail/backdrop）的 Nginx 签名 URL 列表。
    - 鉴权在服务层进行
    - 资源路径为 {movie_id}/{image_file}
    - 使用 Nginx 分发具体文件（secure_link）
    - 当 image=all 时，每个影片返回三条 URL，顺序：poster → thumbnail → backdrop
    """
    logger.info(f"获取 {image} 签名 URL 列表，影片ID列表：{ids}")
    return await movie_service.list_movie_covers_signed(
        ids,
        kind=image,
        current_user=current_user,
    )

# 创建电影
@router.post("/", response_model=MovieCreateResponseSchema)
@router_handler(action="create_movie")
async def create_movie(
    request: Request,
    data: MovieCreateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    data_dict = data.model_dump(exclude_unset=True)
    if "library_id" not in data_dict:
        raise HTTPException(status_code=400, detail="library_id 不能为空")
    payload = MovieCreate(**data_dict)
    movie_info, task_id = await movie_service.create_movie(
        payload, current_user=current_user
    )
    return {"movie_info": movie_info, "task_id": task_id}

# 异步批量导入
@router.post("/bulk", response_model=TaskReadResponseSchema)
@router_handler(action="import_movies_bulk")
@idempotent()
async def import_movies_batch(
    request: Request,
    library_id: str = Query(..., description="媒体库ID"),
    file: UploadFile = File(..., description="包含电影数据的 JSON 文件"),
    current_user=Depends(get_current_user),
):
    task_model, task_info = await movie_service.import_movies_from_file(
        file, current_user=current_user, library_id=library_id
    )
    return task_model

# 更新电影-多个
@router.patch("/batch", response_model=List[MovieReadResponseSchema])
@router_handler(action="update_movies_batch")
async def update_movies(
    request: Request,
    data: MovieBatchUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    patch_model = MovieUpdate(**data.patch.model_dump(exclude_unset=True))
    return await movie_service.update_movies_by_ids(
        data.movie_ids,
        patch_model,
        current_user=current_user,
    )


# 更新电影-单个
@router.patch("/{movie_id}", response_model=MovieReadResponseSchema)
@router_handler(action="update_movie")
async def update_movie(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    patch: MovieUpdateRequestSchema = Body(...),
    current_user=Depends(get_current_user),
):
    patch_model = MovieUpdate(**patch.model_dump(exclude_unset=True))
    result = await movie_service.update_movies_by_ids(
        [movie_id], patch_model, current_user=current_user
    )
    if not result:
        raise NotFoundError(f"电影ID {movie_id} 不存在")
    return result[0]


# 删除电影-多个
@router.delete("/bulk", response_model=dict)
@router_handler(action="delete_movies_bulk")
async def delete_movies(
    request: Request,
    movie_ids: List[str] = Body(..., description="影片ID列表"),
    soft_delete: bool = Query(False, description="是否软删除"),
    current_user=Depends(get_current_user),
):
    outcome = await movie_service.delete_movies_by_ids(
        movie_ids,
        current_user=current_user,
        soft_delete=soft_delete,
    )
    return {"message": outcome["message"], "success": outcome["success"], "failed": outcome["failed"]}

# 删除电影-单个
@router.delete("/{movie_id}", response_model=dict)
@router_handler(action="delete_movie")
async def delete_movie(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    soft_delete: bool = Query(False, description="是否软删除"),
    current_user=Depends(get_current_user),
):
    outcome = await movie_service.delete_movies_by_ids(
        [movie_id],
        current_user=current_user,
        soft_delete=soft_delete,
    )
    return {"message": outcome["message"], "success": outcome["success"], "failed": outcome["failed"]}

# 重建
@router.post("/restore", response_model=List[MovieReadResponseSchema])
@router_handler(action="restore_movies")
async def restore_movies(
    request: Request,
    movie_ids: List[str] = Body(..., description="待恢复的影片ID列表"),
    current_user=Depends(get_current_user),
):
    return await movie_service.restore_movies_by_ids(
        movie_ids, current_user=current_user
    )

# 更换电影封面（poster.jpg）
@router.post("/{movie_id}/poster", response_model=MovieReadResponseSchema)
@router_handler(action="replace_movie_poster")
async def replace_movie_poster(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    file: UploadFile = File(..., description="海报文件（jpg/png）"),
    current_user=Depends(get_current_user),
):
    return await movie_service.replace_movie_poster(
        movie_id, file, current_user=current_user
    )

# 批量更换电影图片（poster.jpg / backdrop.jpg）
@router.post("/{movie_id}/images", response_model=MovieReadResponseSchema)
@router_handler(action="replace_movie_images")
async def replace_movie_images(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    files: List[UploadFile] = File(..., description="图片文件（支持多个）"),
    types: List[str] = Form(..., description="图片类型列表：poster|backdrop，与文件一一对应"),
    current_user=Depends(get_current_user),
):
    return await movie_service.replace_movie_images(
        movie_id, files, types, current_user=current_user
    )

# 爬取元数据（后台任务）
@router.post("/{movie_id}/metadata/scrape", response_model=TaskReadResponseSchema)
@router_handler(action="scrape_movie_metadata")
async def scrape_movie_metadata(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    plugin_names: Optional[List[str]] = Body(None, description="插件列表，不传则使用库激活的插件"),
    current_user=Depends(get_current_user),
):
    task_model, _ = await movie_service.scrape_movie_metadata(
        movie_id, plugin_names, current_user=current_user
    )
    return task_model

# 爬取字幕（后台任务）
@router.post("/{movie_id}/subtitles/scrape", response_model=TaskReadResponseSchema)
@router_handler(action="scrape_movie_subtitles")
async def scrape_movie_subtitles(
    request: Request,
    movie_id: str = Path(..., description="影片ID"),
    plugin_names: Optional[List[str]] = Body(None, description="插件列表，不传则使用库激活的插件"),
    current_user=Depends(get_current_user),
):
    task_model, _ = await movie_service.scrape_movie_subtitles(
        movie_id, plugin_names, current_user=current_user
    )
    return task_model

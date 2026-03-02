from langchain.tools import tool, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
from src.services.movies.movie_service import MovieService
from src.agent.tools.builders import build_movie_create_payload


class ListMoviesSchema(BaseModel):
    query: Optional[str] = Field(default=None, description="搜索关键词")
    genres: Optional[List[str]] = Field(default=None, description="类型筛选")
    min_rating: Optional[float] = Field(default=None, description="最低评分")
    max_rating: Optional[float] = Field(default=None, description="最高评分")
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")
    tags: Optional[List[str]] = Field(default=None, description="标签筛选")
    is_deleted: Optional[bool] = Field(default=None, description="是否已删除")
    page: int = Field(default=1, description="页码")
    size: int = Field(default=20, description="每页数量")
    sort_by: Optional[str] = Field(default=None, description="排序字段")
    sort_dir: Optional[int] = Field(default=None, description="排序方向 1/-1")
    library_id: Optional[str] = Field(default=None, description="指定媒体库ID")


class GetMovieSchema(BaseModel):
    movie_id: str = Field(description="电影ID")


class CreateMovieSchema(BaseModel):
    library_id: str = Field(description="媒体库ID")
    title: str = Field(description="原标题")
    title_cn: Optional[str] = Field(default=None, description="原标题翻译")
    directors: Optional[List[str]] = Field(default=None, description="导演")
    actors: Optional[List[str]] = Field(default=None, description="演员")
    description: Optional[str] = Field(default=None, description="原描述")
    description_cn: Optional[str] = Field(default=None, description="描述翻译")
    release_date: Optional[str] = Field(default=None, description="上映日期 YYYY-MM-DD")
    genres: Optional[List[str]] = Field(default=None, description="类型，往往是官方标签")
    rating: Optional[float] = Field(default=None, description="评分，0-10")
    tags: Optional[List[str]] = Field(default=None, description="标签，用户自行维护的标签")


class UpdateMoviesByIdsSchema(BaseModel):
    movie_ids: List[str] = Field(description="电影ID列表")
    title: Optional[str] = Field(default=None, description="原标题")
    title_cn: Optional[str] = Field(default=None, description="标题翻译")
    directors: Optional[List[str]] = Field(default=None, description="导演")
    actors: Optional[List[str]] = Field(default=None, description="演员")
    description: Optional[str] = Field(default=None, description="原描述")
    description_cn: Optional[str] = Field(default=None, description="描述翻译")
    release_date: Optional[str] = Field(default=None, description="上映日期 YYYY-MM-DD")
    genres: Optional[List[str]] = Field(default=None, description="类型，往往是官方标签，如 drama 这种 TMDB 英文标签")
    rating: Optional[float] = Field(default=None, description="评分")
    tags: Optional[List[str]] = Field(default=None, description="标签，用户自行维护的标签")


class DeleteMoviesByIdsSchema(BaseModel):
    movie_ids: List[str] = Field(description="电影ID列表")
    soft_delete: bool = Field(default=True, description="是否软删除")


class RestoreMoviesByIdsSchema(BaseModel):
    movie_ids: List[str] = Field(description="电影ID列表")


@tool(args_schema=ListMoviesSchema)
async def list_movies_tool(
    query: Optional[str],
    genres: Optional[List[str]],
    min_rating: Optional[float],
    max_rating: Optional[float],
    start_date: Optional[str],
    end_date: Optional[str],
    tags: Optional[List[str]],
    is_deleted: Optional[bool],
    page: int,
    size: int,
    sort_by: Optional[str],
    sort_dir: Optional[int],
    library_id: Optional[str],
    runtime: ToolRuntime,
) -> str:
    """列出电影库中的电影。支持关键词、类型、评分、日期、标签筛选，支持分页与排序。"""
    current_user = runtime.context.get("user")
    service = MovieService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_movies(
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
        return f"电影列表: {result.model_dump_json()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


@tool(args_schema=GetMovieSchema)
async def get_movie_tool(
    movie_id: str,
    runtime: ToolRuntime,
) -> str:
    """获取单个电影的详情。"""
    current_user = runtime.context.get("user")
    service = MovieService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_movie(movie_id, current_user=current_user)
        return f"电影详情: {result.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


@tool(args_schema=CreateMovieSchema)
async def create_movie_tool(
    library_id: str,
    title: str,
    title_cn: Optional[str],
    directors: Optional[List[str]],
    actors: Optional[List[str]],
    description: Optional[str],
    description_cn: Optional[str],
    release_date: Optional[str],
    genres: Optional[List[str]],
    rating: Optional[float],
    tags: Optional[List[str]],
    runtime: ToolRuntime,
) -> str:
    """创建电影记录并触发后台任务入库或扫描。"""
    current_user = runtime.context.get("user")
    service = MovieService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        # 使用统一的构造函数，复用HTTP路由的逻辑
        data = build_movie_create_payload(
            library_id=library_id,
            title=title,
            title_cn=title_cn,
            directors=directors,
            actors=actors,
            description=description,
            description_cn=description_cn,
            release_date=release_date,
            genres=genres,
            rating=rating,
            tags=tags
        )
        created, task_id = await service.create_movie(data, current_user=current_user)
        return f"电影创建成功: {created.id}, 任务: {task_id}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


@tool(args_schema=UpdateMoviesByIdsSchema)
async def update_movies_by_ids_tool(
    movie_ids: List[str],
    title: Optional[str],
    title_cn: Optional[str],
    directors: Optional[List[str]],
    actors: Optional[List[str]],
    description: Optional[str],
    description_cn: Optional[str],
    release_date: Optional[str],
    genres: Optional[List[str]],
    rating: Optional[float],
    tags: Optional[List[str]],
    runtime: ToolRuntime,
) -> str:
    """批量更新多部电影的元数据（标题、类型、评分等）。"""
    current_user = runtime.context.get("user")
    service = MovieService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        from src.models import MovieUpdate
        patch_payload = {
            "title": title,
            "title_cn": title_cn,
            "directors": directors,
            "actors": actors,
            "description": description,
            "description_cn": description_cn,
            "release_date": release_date,
            "genres": genres,
            "rating": rating,
            "tags": tags,
        }
        patch = MovieUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        result = await service.update_movies_by_ids(movie_ids, patch, current_user=current_user)
        return f"电影更新成功: {len(result)} 项"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


@tool(args_schema=DeleteMoviesByIdsSchema)
async def delete_movies_by_ids_tool(
    movie_ids: List[str],
    soft_delete: bool,
    runtime: ToolRuntime,
) -> str:
    """批量删除电影，支持软删除。"""
    current_user = runtime.context.get("user")
    service = MovieService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.delete_movies_by_ids(movie_ids, current_user=current_user, soft_delete=soft_delete)
        return f"删除完成: {result}"
    except Exception as e:
        return f"删除失败: {str(e)}"


@tool(args_schema=RestoreMoviesByIdsSchema)
async def restore_movies_by_ids_tool(
    movie_ids: List[str],
    runtime: ToolRuntime,
) -> str:
    """批量恢复已删除电影。"""
    current_user = runtime.context.get("user")
    service = MovieService()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.restore_movies_by_ids(movie_ids, current_user=current_user)
        return f"恢复成功: {len(result)} 项"
    except Exception as e:
        return f"恢复失败: {str(e)}"

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from src.models import MovieCreate, MovieUpdate, UserRole

from .base import ToolDefinition
from .registry import ToolRegistry
from ..types import RequestContext


class ListMoviesSchema(BaseModel):
    """列出电影参数模型。"""

    query: Optional[str] = Field(default=None, description="搜索关键词")
    genres: Optional[List[str]] = Field(default=None, description="类型筛选")
    min_rating: Optional[float] = Field(default=None, ge=0, le=10, description="最低评分")
    max_rating: Optional[float] = Field(default=None, ge=0, le=10, description="最高评分")
    start_date: Optional[str] = Field(default=None, description="开始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")
    tags: Optional[List[str]] = Field(default=None, description="标签筛选")
    is_deleted: Optional[bool] = Field(default=None, description="是否已删除")
    page: int = Field(default=1, ge=1, description="页码")
    size: int = Field(default=20, ge=1, le=200, description="每页数量")
    sort_by: Optional[str] = Field(default=None, description="排序字段")
    sort_dir: Optional[int] = Field(default=None, description="排序方向 1/-1")
    library_id: Optional[str] = Field(default=None, description="指定媒体库ID")


class GetMovieSchema(BaseModel):
    """获取电影详情参数模型。"""

    movie_id: str = Field(description="电影ID")


class CreateMovieSchema(BaseModel):
    """创建电影参数模型。"""

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
    """批量更新电影参数模型。"""

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
    """批量删除电影参数模型。"""

    movie_ids: List[str] = Field(description="电影ID列表")
    soft_delete: bool = Field(default=False, description="是否软删除")


class RestoreMoviesByIdsSchema(BaseModel):
    """批量恢复电影参数模型。"""

    movie_ids: List[str] = Field(description="电影ID列表")


@dataclass
class _FallbackUser:
    id: str
    username: str = "fallback_user"
    role: str = UserRole.USER


async def _get_current_user(ctx: Optional[RequestContext]) -> Optional[Any]:
    """根据上下文获取当前用户对象。"""
    if ctx is None:
        return None
    try:
        from src.logic.users.user_logic import UserLogic

        logic = UserLogic()
        return await logic.get_user(ctx.user_id)
    except Exception:
        return _FallbackUser(id=ctx.user_id, role=UserRole.USER)


def _get_movie_service() -> Any:
    """获取 MovieService 实例。"""
    from src.services.movies.movie_service import MovieService

    return MovieService()


def _schema(model: type[BaseModel]) -> Dict[str, Any]:
    """生成 JSON Schema。"""
    return model.model_json_schema()


def _validate_schema(model: type[BaseModel], **kwargs: Any) -> BaseModel | ValidationError:
    """校验并返回参数模型。"""
    try:
        return model(**kwargs)
    except ValidationError as exc:
        return exc


async def list_movies_tool(
    query: Optional[str] = None,
    genres: Optional[List[str]] = None,
    min_rating: Optional[float] = None,
    max_rating: Optional[float] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tags: Optional[List[str]] = None,
    is_deleted: Optional[bool] = None,
    page: int = 1,
    size: int = 20,
    sort_by: Optional[str] = None,
    sort_dir: Optional[int] = None,
    library_id: Optional[str] = None,
    ctx: Optional[RequestContext] = None,
) -> str:
    """列出电影库中的电影。"""
    validated = _validate_schema(
        ListMoviesSchema,
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
        library_id=library_id,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if validated.sort_dir not in (None, 1, -1):
        return "参数验证失败: sort_dir 仅支持 1 或 -1"
    current_user = await _get_current_user(ctx)
    service = _get_movie_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.list_movies(
            query=validated.query,
            genres=validated.genres,
            min_rating=validated.min_rating,
            max_rating=validated.max_rating,
            start_date=validated.start_date,
            end_date=validated.end_date,
            tags=validated.tags,
            is_deleted=validated.is_deleted,
            page=validated.page,
            size=validated.size,
            sort_by=validated.sort_by,
            sort_dir=validated.sort_dir,
            current_user=current_user,
            library_id=validated.library_id,
        )
        return f"电影列表: {result.model_dump_json()}"
    except Exception as e:
        return f"查询失败: {str(e)}"


async def get_movie_tool(
    movie_id: str,
    ctx: Optional[RequestContext] = None,
) -> str:
    """获取单个电影的详情。"""
    if not movie_id:
        return "参数验证失败: movie_id 不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_movie_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.get_movie(movie_id, current_user=current_user)
        return f"电影详情: {result.model_dump()}"
    except Exception as e:
        return f"获取失败: {str(e)}"


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
    ctx: Optional[RequestContext] = None,
) -> str:
    """创建电影记录并触发后台任务入库或扫描。"""
    validated = _validate_schema(
        CreateMovieSchema,
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
        tags=tags,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    current_user = await _get_current_user(ctx)
    service = _get_movie_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        data = MovieCreate(**validated.model_dump(exclude_none=True))
        created, task_id = await service.create_movie(data, current_user=current_user)
        if task_id:
            return f"电影创建成功: {created.id}, 任务: {task_id}"
        return f"电影创建成功: {created.id}"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"创建失败: {str(e)}"


async def update_movies_by_ids_tool(
    movie_ids: List[str],
    title: Optional[str] = None,
    title_cn: Optional[str] = None,
    directors: Optional[List[str]] = None,
    actors: Optional[List[str]] = None,
    description: Optional[str] = None,
    description_cn: Optional[str] = None,
    release_date: Optional[str] = None,
    genres: Optional[List[str]] = None,
    rating: Optional[float] = None,
    tags: Optional[List[str]] = None,
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量更新多部电影的元数据。"""
    validated = _validate_schema(
        UpdateMoviesByIdsSchema,
        movie_ids=movie_ids,
        title=title,
        title_cn=title_cn,
        directors=directors,
        actors=actors,
        description=description,
        description_cn=description_cn,
        release_date=release_date,
        genres=genres,
        rating=rating,
        tags=tags,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.movie_ids:
        return "参数验证失败: 电影ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_movie_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        patch_payload = {
            "title": validated.title,
            "title_cn": validated.title_cn,
            "directors": validated.directors,
            "actors": validated.actors,
            "description": validated.description,
            "description_cn": validated.description_cn,
            "release_date": validated.release_date,
            "genres": validated.genres,
            "rating": validated.rating,
            "tags": validated.tags,
        }
        patch = MovieUpdate(**{k: v for k, v in patch_payload.items() if v is not None})
        result = await service.update_movies_by_ids(validated.movie_ids, patch, current_user=current_user)
        return f"电影更新成功: {len(result)} 项"
    except ValidationError as e:
        return f"参数验证失败: {str(e)}"
    except Exception as e:
        return f"更新失败: {str(e)}"


async def delete_movies_by_ids_tool(
    movie_ids: List[str],
    soft_delete: bool,
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量删除电影，支持软删除。"""
    validated = _validate_schema(
        DeleteMoviesByIdsSchema,
        movie_ids=movie_ids,
        soft_delete=soft_delete,
    )
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.movie_ids:
        return "参数验证失败: 电影ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_movie_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.delete_movies_by_ids(
            validated.movie_ids,
            current_user=current_user,
            soft_delete=validated.soft_delete,
        )
        return f"删除完成: {result}"
    except Exception as e:
        return f"删除失败: {str(e)}"


async def restore_movies_by_ids_tool(
    movie_ids: List[str],
    ctx: Optional[RequestContext] = None,
) -> str:
    """批量恢复已删除电影。"""
    validated = _validate_schema(RestoreMoviesByIdsSchema, movie_ids=movie_ids)
    if isinstance(validated, ValidationError):
        return f"参数验证失败: {validated}"
    if not validated.movie_ids:
        return "参数验证失败: 电影ID列表不能为空"
    current_user = await _get_current_user(ctx)
    service = _get_movie_service()
    if current_user is None:
        return "错误：无法获取当前用户信息。请联系管理员。"
    try:
        result = await service.restore_movies_by_ids(validated.movie_ids, current_user=current_user)
        return f"恢复成功: {len(result)} 项"
    except Exception as e:
        return f"恢复失败: {str(e)}"


def register_movie_tools(registry: ToolRegistry) -> None:
    """注册电影相关工具。"""
    registry.register(
        ToolDefinition(
            name="list_movies",
            description="列出电影库中的电影。",
            parameters=_schema(ListMoviesSchema),
            handler=list_movies_tool,
            category="movies",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_movie",
            description="获取单个电影的详情。",
            parameters=_schema(GetMovieSchema),
            handler=get_movie_tool,
            category="movies",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_movie",
            description="创建电影记录并触发后台任务入库或扫描。",
            parameters=_schema(CreateMovieSchema),
            handler=create_movie_tool,
            category="movies",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_movies_by_ids",
            description="批量更新多部电影的元数据。",
            parameters=_schema(UpdateMoviesByIdsSchema),
            handler=update_movies_by_ids_tool,
            category="movies",
        )
    )
    registry.register(
        ToolDefinition(
            name="delete_movies_by_ids",
            description="批量删除电影，支持软删除。",
            parameters=_schema(DeleteMoviesByIdsSchema),
            handler=delete_movies_by_ids_tool,
            category="movies",
            requires_confirmation=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="restore_movies_by_ids",
            description="批量恢复已删除电影。",
            parameters=_schema(RestoreMoviesByIdsSchema),
            handler=restore_movies_by_ids_tool,
            category="movies",
        )
    )

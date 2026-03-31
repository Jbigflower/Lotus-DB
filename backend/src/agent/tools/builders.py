from typing import Any, Dict, List, Optional

from src.models import (
    AssetCreate,
    AssetStoreType,
    AssetType,
    CustomListCreate,
    CustomListType,
    LibraryCreate,
    LibraryType,
    MovieCreate,
    UserAssetCreate,
    UserAssetType,
    WatchHistoryCreate,
    WatchType,
)


def build_library_create_payload(
    name: str,
    library_type: str,
    description: str,
    is_public: bool,
    metadata_plugins: Optional[List[str]] = None,
    subtitle_plugins: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> LibraryCreate:
    """构建 LibraryCreate 模型。"""

    activated_plugins = {
        "metadata": metadata_plugins or [],
        "subtitle": subtitle_plugins or [],
    }
    payload: Dict[str, Any] = {
        "name": name,
        "type": LibraryType(library_type),
        "description": description,
        "is_public": is_public,
        "user_id": user_id,
        "root_path": "temp",
        "activated_plugins": activated_plugins,
    }
    payload.update(kwargs)
    return LibraryCreate(**payload)


def build_asset_create_payload(
    library_id: str,
    movie_id: str,
    type: str,
    name: str,
    store_type: str = "Local",
    **kwargs: Any,
) -> AssetCreate:
    """构建 AssetCreate 模型。"""

    payload: Dict[str, Any] = {
        "library_id": library_id,
        "movie_id": movie_id,
        "type": AssetType(type),
        "name": name,
        "path": "temp",
        "store_type": AssetStoreType(store_type),
        "actual_path": None,
        "description": "",
        "tags": [],
    }
    payload.update(kwargs)
    return AssetCreate(**payload)


def build_movie_create_payload(
    library_id: str,
    title: str,
    title_cn: Optional[str] = None,
    directors: Optional[List[str]] = None,
    actors: Optional[List[str]] = None,
    description: Optional[str] = None,
    description_cn: Optional[str] = None,
    release_date: Optional[str] = None,
    genres: Optional[List[str]] = None,
    rating: Optional[float] = None,
    tags: Optional[List[str]] = None,
    **kwargs: Any,
) -> MovieCreate:
    """构建 MovieCreate 模型。"""

    payload: Dict[str, Any] = {
        "library_id": library_id,
        "title": title,
        "title_cn": title_cn,
        "directors": directors or [],
        "actors": actors or [],
        "description": description or "",
        "description_cn": description_cn,
        "release_date": release_date,
        "genres": genres or [],
        "rating": rating,
        "tags": tags or [],
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    payload.update(kwargs)
    return MovieCreate(**payload)


def build_custom_list_create_payload(
    name: str,
    type: str,
    description: Optional[str] = None,
    is_public: bool = False,
    movies: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> CustomListCreate:
    """构建 CustomListCreate 模型。"""

    payload: Dict[str, Any] = {
        "name": name,
        "type": CustomListType(type),
        "description": description or "",
        "movies": movies or [],
        "is_public": is_public,
        "user_id": user_id,
    }
    payload.update(kwargs)
    return CustomListCreate(**payload)


def build_user_asset_create_payload(
    movie_id: str,
    type: str,
    name: Optional[str] = None,
    content: Optional[str] = None,
    related_movie_ids: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    is_public: bool = False,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> UserAssetCreate:
    """构建 UserAssetCreate 模型。"""

    if not name:
        if type in ["note", "review"] and content:
            preview = str(content).strip()
            name = preview[:20] or "untitled"
        else:
            name = "untitled"
    if type in ["note", "review"]:
        import datetime

        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = f"{movie_id}/{type}/{ts}.md"
    else:
        path = "placeholder"
    payload: Dict[str, Any] = {
        "movie_id": movie_id,
        "type": UserAssetType(type),
        "name": name,
        "path": path,
        "store_type": "local",
        "actual_path": None,
        "content": content,
        "related_movie_ids": related_movie_ids or [],
        "tags": tags or [],
        "is_public": is_public,
        "permissions": [],
        "user_id": user_id,
    }
    payload.update(kwargs)
    return UserAssetCreate(**payload)


def build_watch_history_create_payload(
    asset_id: str,
    type: str,
    last_position: int = 0,
    total_duration: int = 0,
    movie_id: Optional[str] = None,
    subtitle_enabled: bool = False,
    subtitle_id: Optional[str] = None,
    subtitle_sync_data: Optional[int] = None,
    playback_rate: float = 1.0,
    user_id: Optional[str] = None,
    **kwargs: Any,
) -> WatchHistoryCreate:
    """构建 WatchHistoryCreate 模型。"""

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "asset_id": asset_id,
        "movie_id": movie_id,
        "type": WatchType(type),
        "last_position": last_position,
        "total_duration": total_duration,
        "subtitle_enabled": subtitle_enabled,
        "subtitle_id": subtitle_id,
        "subtitle_sync_data": subtitle_sync_data,
        "playback_rate": playback_rate,
    }
    payload.update(kwargs)
    return WatchHistoryCreate(**payload)

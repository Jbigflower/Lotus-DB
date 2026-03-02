"""
公共构造函数模块 - 用于统一HTTP路由和Agent工具的模型构建逻辑
遵循《Agent Tool 校验手册》的核心要求：Agent工具路径必须复用HTTP路由创建逻辑
"""

from typing import Dict, Any, Optional, List
from src.models import (
    LibraryCreate, LibraryType,
    AssetCreate, AssetType, AssetStoreType,
    MovieCreate,
    CustomListCreate, CustomListType,
    UserAssetCreate, UserAssetType,
    WatchHistoryCreate, WatchType
)


def build_library_create_payload(
    name: str,
    library_type: str,
    description: str,
    is_public: bool,
    metadata_plugins: Optional[List[str]] = None,
    subtitle_plugins: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    **kwargs
) -> LibraryCreate:
    """
    统一构建 LibraryCreate 模型的公共函数
    
    Args:
        name: 媒体库名称
        library_type: 媒体库类型 ('movie' 或 'tv')
        description: 媒体库描述
        is_public: 是否公开
        metadata_plugins: 元数据插件列表
        subtitle_plugins: 字幕插件列表
        user_id: 用户ID
        **kwargs: 其他可选参数
    
    Returns:
        LibraryCreate: 构建好的模型实例
    """
    # 将两类插件选择转换为 activated_plugins 映射
    activated_plugins = {
        "metadata": metadata_plugins or [],
        "subtitle": subtitle_plugins or [],
    }
    
    # 构建基础payload
    payload = {
        "name": name,
        "type": LibraryType(library_type),
        "description": description,
        "is_public": is_public,
        "user_id": user_id,
        "root_path": "temp",  # 服务层将更新为库ID
        "activated_plugins": activated_plugins,
    }
    
    # 添加其他可选参数
    payload.update(kwargs)
    
    return LibraryCreate(**payload)


def build_asset_create_payload(
    library_id: str,
    movie_id: str,
    type: str,
    name: str,
    store_type: str = "Local",
    **kwargs
) -> AssetCreate:
    """
    统一构建 AssetCreate 模型的公共函数
    
    Args:
        library_id: 媒体库ID
        movie_id: 电影ID
        type: 资产类型 ('video', 'subtitle', 'image')
        name: 资产名称
        store_type: 存储类型
        **kwargs: 其他可选参数
    
    Returns:
        AssetCreate: 构建好的模型实例
    """
    payload = {
        "library_id": library_id,
        "movie_id": movie_id,
        "type": AssetType(type),
        "name": name,
        "path": "temp",  # 服务层将更新为实际路径
        "store_type": AssetStoreType(store_type),
        "actual_path": None,
        "description": "",
        "tags": [],
    }
    
    # 添加其他可选参数
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
    **kwargs
) -> MovieCreate:
    """
    统一构建 MovieCreate 模型的公共函数
    
    Args:
        library_id: 媒体库ID
        title: 原标题
        title_cn: 中文标题
        directors: 导演列表
        actors: 演员列表
        description: 原描述
        description_cn: 中文描述
        release_date: 上映日期
        genres: 类型列表
        rating: 评分
        tags: 标签列表
        **kwargs: 其他可选参数
    
    Returns:
        MovieCreate: 构建好的模型实例
    """
    payload = {
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
    
    # 移除None值
    payload = {k: v for k, v in payload.items() if v is not None}
    
    # 添加其他可选参数
    payload.update(kwargs)
    
    return MovieCreate(**payload)


def build_custom_list_create_payload(
    name: str,
    type: str,
    description: Optional[str] = None,
    is_public: bool = False,
    movies: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    **kwargs
) -> CustomListCreate:
    """
    统一构建 CustomListCreate 模型的公共函数
    
    Args:
        name: 片单名称
        type: 片单类型 ('favorite', 'watchlist', 'customlist')
        description: 描述
        is_public: 是否公开
        movies: 电影ID列表
        user_id: 用户ID
        **kwargs: 其他可选参数
    
    Returns:
        CustomListCreate: 构建好的模型实例
    """
    payload = {
        "name": name,
        "type": CustomListType(type),
        "description": description or "",
        "movies": movies or [],
        "is_public": is_public,
        "user_id": user_id,
    }
    
    # 添加其他可选参数
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
    **kwargs
) -> UserAssetCreate:
    """
    统一构建 UserAssetCreate 模型的公共函数
    
    Args:
        movie_id: 电影ID
        type: 资产类型 ('note', 'review', 'screenshot', 'clip')
        name: 资产名称
        content: 文本内容（note/review类型）
        related_movie_ids: 关联电影ID列表
        tags: 标签列表
        is_public: 是否公开
        user_id: 用户ID
        **kwargs: 其他可选参数
    
    Returns:
        UserAssetCreate: 构建好的模型实例
    """
    # 根据类型生成默认名称
    if not name:
        if type in ["note", "review"] and content:
            preview = str(content).strip()
            name = preview[:20] or "untitled"
        else:
            name = "untitled"
    
    # 根据类型生成路径
    if type in ["note", "review"]:
        import datetime
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = f"{movie_id}/{type}/{ts}.md"
    else:
        path = "placeholder"
    
    payload = {
        "movie_id": movie_id,
        "type": UserAssetType(type),
        "name": name,
        "path": path,
        "store_type": "local",  # 默认本地存储
        "actual_path": None,
        "content": content,
        "related_movie_ids": related_movie_ids or [],
        "tags": tags or [],
        "is_public": is_public,
        "permissions": [],
        "user_id": user_id,
    }
    
    # 添加其他可选参数
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
    **kwargs
) -> WatchHistoryCreate:
    """
    统一构建 WatchHistoryCreate 模型的公共函数
    
    Args:
        asset_id: 资产ID
        type: 观看类型 ('Official', 'Community')
        last_position: 最后观看位置（秒）
        total_duration: 媒体总时长（秒）
        movie_id: 电影ID
        subtitle_enabled: 是否启用字幕
        subtitle_id: 字幕ID
        subtitle_sync_data: 字幕同步（秒）
        playback_rate: 播放倍速
        user_id: 用户ID
        **kwargs: 其他可选参数
    
    Returns:
        WatchHistoryCreate: 构建好的模型实例
    """
    payload = {
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
    
    # 添加其他可选参数
    payload.update(kwargs)
    
    return WatchHistoryCreate(**payload)
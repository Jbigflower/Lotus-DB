from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from datetime import date
from pathlib import Path

from src.models import MovieCreate, AssetCreate


class PluginType(str, Enum):
    """插件类型分类：元数据/海报/头像 与 字幕"""
    METADATA = "metadata"
    SUBTITLE = "subtitle"


class BasePlugin(ABC):
    """
    插件基础接口（所有插件的共同部分）
    - name: 插件名称（唯一标识）
    - provider: 数据来源/平台（如 TMDB、OMDB、OpenSubtitles）
    - version: 插件版本号
    - plugin_type: 插件类型（metadata/subtitle）
    """

    name: str
    provider: str
    version: str
    plugin_type: PluginType

    def __init__(self, name: str, provider: str, version: str, plugin_type: PluginType):
        self.name = name
        self.provider = provider
        self.version = version
        self.plugin_type = plugin_type

    async def setup(self, **kwargs) -> None:
        """插件初始化（可选：如设置 API Key、代理、超时等）"""
        return None

    async def teardown(self) -> None:
        """插件清理（可选）"""
        return None


class MetadataPlugin(BasePlugin, ABC):
    """
    影片元数据/图片/头像 插件接口
    - fetch_movie_metadata: 返回标准 MovieCreate（需服务层提供 library_id）
    - download_artwork: 下载海报/背景图到指定目录
    - download_actor_portrait: 下载演员头像到指定目录
    """

    def __init__(self, name: str, provider: str, version: str):
        super().__init__(name=name, provider=provider, version=version, plugin_type=PluginType.METADATA)

    # 批量获取影片元数据（新增）
    @abstractmethod
    async def fetch_movies_metadata(
        self,
        titles: list[str],
        library_id: str,
        release_dates: Optional[list[Optional[date]]] = None,
    ) -> list[MovieCreate]:
        """
        批量影片元数据获取（参数改为分列，library_id 必填）
        入参：
        - titles: 影片标题列表
        - release_dates: 与 titles 对齐的发布日期列表（可选）
        - library_id: 所属库ID（必填，批量一致）
        返回：
        - List[MovieCreate]，与 titles 顺序一致
        """
        raise NotImplementedError

    # 保留单个方法作为包装器（调用批量方法）
    async def fetch_movie_metadata(
        self,
        title: str,
        library_id: str = None,
        release_date: Optional[date] = None,
    ) -> MovieCreate:
        """
        单个影片元数据获取（包装器，library_id 必填）
        """
        results = await self.fetch_movies_metadata([title], [release_date] if release_date is not None else None, library_id)
        return results[0] if results else MovieCreate(
            library_id=library_id,
            title=title,
            title_cn="",
            directors=[],
            actors=[],
            description="",
            description_cn="",
            release_date=release_date,
            genres=[],
            metadata=None,
            rating=None,
            tags=[],
        )

    # 批量下载海报/背景/缩略图（新增）
    @abstractmethod
    async def download_artworks(
        self,
        titles: list[str],
        dest_dirs: list[str | Path],
        release_dates: Optional[list[Optional[date]]] = None,
    ) -> list[dict[str, Optional[str]]]:
        """
        批量下载海报资源（参数改为分列）
        入参：
        - titles: 影片标题列表
        - dest_dirs: 与 titles 对齐的存储目录列表
        - release_dates: 与 titles 对齐的发布日期列表（可选）
        返回：
        - List[Dict]，每个 Dict 包含:
          { "poster": Optional[str], "backdrop": Optional[str], "thumbnail": Optional[str] }
          值为已保存文件绝对路径或 None；顺序与输入一致
        """
        raise NotImplementedError

    # 保留单个方法作为包装器（调用批量方法）
    async def download_artwork(
        self,
        title: str,
        dest_dir: str | Path,
        release_date: Optional[date] = None,
    ) -> dict[str, Optional[str]]:
        """
        单个影片海报资源下载（包装器）
        返回 Dict: {poster, backdrop, thumbnail}
        """
        results = await self.download_artworks([title], [dest_dir], [release_date] if release_date is not None else None)
        return results[0] if results else {"poster": None, "backdrop": None, "thumbnail": None}

    # 批量下载演员头像（新增，保持与单个方法兼容）
    @abstractmethod
    async def download_actor_portraits(
        self,
        person_names: list[str],
        dest_dirs: list[str | Path],
    ) -> list[bool]:
        """
        批量下载演员头像（参数改为分列）
        入参：
        - person_names: 演员名称列表
        - dest_dirs: 与 person_names 对齐的存储目录列表
        返回：
        - List[bool] 与输入顺序一致
        """
        raise NotImplementedError

    async def download_actor_portrait(
        self,
        person_name: str,
        dest_dir: str | Path,
    ) -> bool:
        """
        单个演员头像下载（包装器）
        """
        results = await self.download_actor_portraits([person_name], [dest_dir])
        return results[0] if results else False


class SubtitlePlugin(BasePlugin, ABC):
    """
    字幕类插件接口
    - find_subtitle_asset: 查找并生成一个标准的 AssetCreate（需服务层提供 movie_id / library_id）
    - download_subtitle: 下载字幕到指定目录
    """

    def __init__(self, name: str, provider: str, version: str):
        super().__init__(name=name, provider=provider, version=version, plugin_type=PluginType.SUBTITLE)

    @abstractmethod
    async def find_subtitle_assets(
        self,
        titles: list[str],
        language: str,
        movie_id: str,
        library_id: str,
    ) -> list[AssetCreate]:
        """
        字幕获取
        入参：
        - titles: 影片标题列表
        - language: 目标语言（如 'zh-CN'）
        - movie_id: 影片ID
        - library_id: 库ID
        返回：
        - AssetCreate（type=subtitle），用于后续创建资产记录
        """
        raise NotImplementedError

    async def find_subtitle_asset(
        self,
        title: str,
        language: str,
        movie_id: str,
        library_id: str,
    ) -> AssetCreate:
        """
        字幕获取（包装器）
        """
        results = await self.find_subtitle_assets([title], language, movie_id, library_id)
        return results[0]

    @abstractmethod
    async def download_subtitles(
        self,
        titles: list[str],
        language: str,
        dest_dir: str | Path,
    ) -> bool:
        """
        字幕下载
        入参：
        - titles: 影片标题列表
        - language: 目标语言
        - dest_dir: 存储目录（绝对路径）
        返回：
        - bool: 是否成功
        """
        raise NotImplementedError
    
    async def download_subtitle(
        self,
        title: str,
        language: str,
        dest_dir: str | Path,
    ) -> bool:
        """
        字幕下载（包装器）
        """
        results = await self.download_subtitles([title], language, dest_dir)
        return results[0] if results else False
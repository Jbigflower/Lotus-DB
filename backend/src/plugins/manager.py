from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional, Type

from config.logging import get_service_logger
from src.plugins.base_plugin import BasePlugin, PluginType, MetadataPlugin, SubtitlePlugin


logger = get_service_logger("plugins.manager")


class PluginManager:
    """
    插件管理器：
    - 扫描 src/plugins/providers 下的模块
    - 加载并注册插件实例
    - 提供按类型/名称检索与便捷执行入口
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, BasePlugin] = {}
        self._by_type: Dict[PluginType, Dict[str, BasePlugin]] = {PluginType.METADATA: {}, PluginType.SUBTITLE: {}}

    def register(self, plugin: BasePlugin) -> None:
        name = plugin.name
        if name in self._plugins:
            logger.warning(f"插件名称冲突，覆盖已注册插件：{name}")
        self._plugins[name] = plugin
        self._by_type[plugin.plugin_type][name] = plugin
        logger.info(f"插件已注册: name={plugin.name}, provider={plugin.provider}, type={plugin.plugin_type}")

    def get(self, name: str) -> Optional[BasePlugin]:
        return self._plugins.get(name)

    def get_by_type(self, ptype: PluginType) -> List[BasePlugin]:
        return list(self._by_type.get(ptype, {}).values())

    def scan_and_load(self, providers_dir: Optional[str | Path] = None) -> None:
        """
        启动时自动扫描并加载插件。
        约定：
        - 插件放在 src/plugins/providers/ 下
        - 可通过模块提供 get_plugins() -> List[BasePlugin] 返回实例
        - 或通过类继承 MetadataPlugin / SubtitlePlugin，且支持无参构造，管理器会自动实例化
        """
        base_pkg = "src.plugins.providers"
        base_path = Path(__file__).resolve().parent / "providers"
        search_path = Path(providers_dir) if providers_dir else base_path

        if not search_path.exists():
            logger.warning(f"插件目录不存在: {search_path}")
            return

        logger.info(f"扫描插件目录: {search_path}")
        for finder, name, is_pkg in pkgutil.walk_packages([str(search_path)]):
            # 构造可导入模块名，如 src.plugins.providers.tmdb
            rel = name  # 相对 providers 根的模块路径
            mod_name = f"{base_pkg}.{rel}"
            try:
                module = importlib.import_module(mod_name)
            except Exception as e:
                logger.error(f"导入插件模块失败: {mod_name}", exc_info=e)
                continue

            # 优先使用模块暴露的 get_plugins() 函数
            if hasattr(module, "get_plugins") and callable(module.get_plugins):
                try:
                    instances = module.get_plugins()
                    for p in instances:
                        if isinstance(p, BasePlugin):
                            self.register(p)
                        else:
                            logger.warning(f"忽略非 BasePlugin 实例: {p}")
                    continue
                except Exception as e:
                    logger.error(f"调用 {mod_name}.get_plugins() 失败", exc_info=e)

            # 回退：扫描类并尝试无参构造
            for attr in module.__dict__.values():
                if inspect.isclass(attr):
                    cls: Type = attr
                    if cls in (BasePlugin, MetadataPlugin, SubtitlePlugin):
                        continue
                    try:
                        if issubclass(cls, (MetadataPlugin, SubtitlePlugin)):
                            instance = cls()  # 需要无参构造
                            if isinstance(instance, BasePlugin):
                                self.register(instance)
                    except TypeError:
                        # 无法无参构造，跳过
                        logger.debug(f"跳过无法无参构造的插件类: {mod_name}.{cls.__name__}")
                    except Exception as e:
                        logger.error(f"实例化插件类失败: {mod_name}.{cls.__name__}", exc_info=e)

        logger.info(f"插件加载完成：总数={len(self._plugins)}")

    def _ordered_candidates(self, ptype: PluginType, prefer_order: Optional[List[str]] = None) -> List[BasePlugin]:
        # 根据 prefer_order 生成优先级列表，随后追加剩余插件
        all_plugins = {p.name: p for p in self.get_by_type(ptype)}
        ordered: List[BasePlugin] = []
        seen: set[str] = set()
        for name in (prefer_order or []):
            p = all_plugins.get(name)
            if p:
                ordered.append(p)
                seen.add(name)
        # 追加未在 prefer_order 中的插件
        for name, p in all_plugins.items():
            if name not in seen:
                ordered.append(p)
        return ordered

    def _prefer_from_activated(self, activated: Optional[dict[str, List[str]]], key: str) -> Optional[List[str]]:
        if not activated:
            return None
        return activated.get(key)

    # 内部工具：规范化 release_date（支持 str ISO8601）
    def _to_date(self, release_date) -> Optional["date"]:
        try:
            from datetime import date as _date, datetime as _datetime
            if release_date is None:
                return None
            if isinstance(release_date, _date):
                return release_date
            if isinstance(release_date, str):
                return _datetime.fromisoformat(release_date).date()
        except Exception:
            return None
        return None

    # --------- 便捷执行入口（服务层可直接使用） --------- #
    async def fetch_movies_metadata(
        self,
        titles: list[str],
        library_id: str,
        release_dates: Optional[list[Optional["date"]]] = None,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> List["MovieCreate"]:
        """
        批量获取电影元数据；按优先顺序选择一个 Metadata 插件并返回结果（library_id 必填）
        """
        from src.models import MovieCreate  # 局部导入以避免循环
        if activated and not prefer_order:
            prefer_order = self._prefer_from_activated(activated, "metadata")
        candidates = self._ordered_candidates(PluginType.METADATA, prefer_order)
        if prefer:
            candidates = sorted(candidates, key=lambda p: 0 if p.name == prefer else 1)

        # 规范化 release_dates
        count = len(titles)
        norm_dates = [
            self._to_date(release_dates[i]) if release_dates and i < len(release_dates) else None
            for i in range(count)
        ]

        for plugin in candidates:
            try:
                if isinstance(plugin, MetadataPlugin):
                    results = await plugin.fetch_movies_metadata(titles, norm_dates, library_id)
                    if results and all(isinstance(m, MovieCreate) for m in results):
                        return results
            except Exception as e:
                logger.error(f"metadata批量插件失败: {plugin.name}", exc_info=e)
        return []

    async def fetch_movie_metadata(
        self,
        title: str,
        library_id: str,
        release_date: Optional["date"] = None,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> Optional["MovieCreate"]:
        """
        单个元数据获取（包装器，library_id 必填）
        """
        results = await self.fetch_movies_metadata(
            [title], [release_date] if release_date is not None else None, library_id, prefer=prefer, prefer_order=prefer_order, activated=activated
        )
        return results[0] if results else None

    async def download_artworks(
        self,
        titles: list[str],
        dest_dirs: list[str | Path],
        release_dates: Optional[list[Optional["date"]]] = None,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> List[dict[str, Optional[str]]]:
        """
        批量下载海报/背景/缩略图；返回与输入顺序一致的列表
        """
        if activated and not prefer_order:
            prefer_order = self._prefer_from_activated(activated, "metadata")
        candidates = self._ordered_candidates(PluginType.METADATA, prefer_order)
        if prefer:
            candidates = sorted(candidates, key=lambda p: 0 if p.name == prefer else 1)

        # 规范化 release_dates
        count = len(titles)
        norm_dates = [
            self._to_date(release_dates[i]) if release_dates and i < len(release_dates) else None
            for i in range(count)
        ]

        for plugin in candidates:
            try:
                if isinstance(plugin, MetadataPlugin):
                    results = await plugin.download_artworks(titles, dest_dirs, norm_dates)
                    if results:
                        return results
            except Exception as e:
                logger.error(f"artwork批量插件失败: {plugin.name}", exc_info=e)
        return [{"poster": None, "backdrop": None, "thumbnail": None} for _ in titles]

    async def download_artwork(
        self,
        title: str,
        dest_dir: str | Path,
        release_date: Optional["date"] = None,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> dict[str, Optional[str]]:
        """
        单个海报下载（包装器）
        返回 Dict: {poster, backdrop, thumbnail}
        """
        results = await self.download_artworks(
            [title], [dest_dir], [release_date] if release_date is not None else None, prefer=prefer, prefer_order=prefer_order, activated=activated
        )
        return results[0] if results else {"poster": None, "backdrop": None, "thumbnail": None}

    async def download_actor_portraits(
        self,
        person_names: list[str],
        dest_dirs: list[str | Path],
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> List[bool]:
        """
        批量下载演员头像；返回与输入顺序一致的布尔列表
        """
        if activated and not prefer_order:
            prefer_order = self._prefer_from_activated(activated, "metadata")
        candidates = self._ordered_candidates(PluginType.METADATA, prefer_order)
        if prefer:
            candidates = sorted(candidates, key=lambda p: 0 if p.name == prefer else 1)
        for plugin in candidates:
            try:
                if isinstance(plugin, MetadataPlugin):
                    results = await plugin.download_actor_portraits(person_names, dest_dirs)
                    if results:
                        return results
            except Exception as e:
                logger.error(f"portrait批量插件失败: {plugin.name}", exc_info=e)
        return [False for _ in person_names]

    async def download_actor_portrait(
        self,
        person_name: str,
        dest_dir: str | Path,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> bool:
        """
        单个演员头像下载（包装器）
        """
        results = await self.download_actor_portraits(
            [person_name], [dest_dir], prefer=prefer, prefer_order=prefer_order, activated=activated
        )
        return results[0] if results else False

    async def find_subtitle_assets(
        self,
        titles: list[str],
        language: str,
        movie_id: str,
        library_id: str,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> List["AssetCreate"]:
        """
        批量字幕资产查找
        """
        from src.models import AssetCreate  # 局部导入以避免循环
        if activated and not prefer_order:
            prefer_order = self._prefer_from_activated(activated, "subtitle")
        candidates = self._ordered_candidates(PluginType.SUBTITLE, prefer_order)
        if prefer:
            candidates = sorted(candidates, key=lambda p: 0 if p.name == prefer else 1)
        for plugin in candidates:
            try:
                if isinstance(plugin, SubtitlePlugin):
                    results = await plugin.find_subtitle_assets(titles, language, movie_id, library_id)
                    if results and all(isinstance(a, AssetCreate) for a in results):
                        return results
            except Exception as e:
                logger.error(f"subtitle批量插件失败: {plugin.name}", exc_info=e)
        return []

    async def find_subtitle_asset(
        self,
        title: str,
        language: str,
        movie_id: str,
        library_id: str,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> Optional["AssetCreate"]:
        """
        单个字幕资产查找（包装器）
        """
        results = await self.find_subtitle_assets(
            [title], language, movie_id, library_id, prefer=prefer, prefer_order=prefer_order, activated=activated
        )
        return results[0] if results else None

    async def download_subtitles(
        self,
        titles: list[str],
        language: str,
        dest_dir: str | Path,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> bool:
        """
        批量字幕下载
        """
        if activated and not prefer_order:
            prefer_order = self._prefer_from_activated(activated, "subtitle")
        candidates = self._ordered_candidates(PluginType.SUBTITLE, prefer_order)
        if prefer:
            candidates = sorted(candidates, key=lambda p: 0 if p.name == prefer else 1)
        for plugin in candidates:
            try:
                if isinstance(plugin, SubtitlePlugin):
                    ok = await plugin.download_subtitles(titles, language, dest_dir)
                    if ok:
                        return True
            except Exception as e:
                logger.error(f"subtitle下载批量插件失败: {plugin.name}", exc_info=e)
        return False

    async def download_subtitle(
        self,
        title: str,
        language: str,
        dest_dir: str | Path,
        prefer: Optional[str] = None,
        prefer_order: Optional[List[str]] = None,
        activated: Optional[dict[str, List[str]]] = None,
    ) -> bool:
        """
        单个字幕下载（包装器）
        """
        return await self.download_subtitles([title], language, dest_dir, prefer=prefer, prefer_order=prefer_order, activated=activated)


# 全局单例
plugin_manager = PluginManager()
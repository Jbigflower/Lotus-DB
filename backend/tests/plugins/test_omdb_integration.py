import os
from datetime import date
from pathlib import Path

import pytest

from src.plugins.providers.omdb import OMDBMetadataPlugin
from src.plugins.manager import PluginManager
from src.plugins.base_plugin import PluginType
from src.models import MovieCreate

# 若未配置环境变量，整个模块跳过（请确保加载 .env 到环境）
OMDB_KEY = os.getenv("OMDB_API_KEY")
if not OMDB_KEY:
    pytest.skip("OMDB_API_KEY 未配置到环境变量，跳过 OMDB 集成测试", allow_module_level=True)


def test_integration_omdb_fetch_metadata_real():
    plugin = OMDBMetadataPlugin()  # 自动从环境变量获取 key
    # 使用真实影片，断言关键字段非空且类型正确
    model = plugin.fetch_movie_metadata(title="Arrival", release_date=date(2016, 11, 11), library_id="lib1")
    assert isinstance(model, MovieCreate)
    assert model.library_id == "lib1"
    assert isinstance(model.title, str) and len(model.title) > 0
    assert model.release_date is not None
    # 评分可能随时间变化，仅检查范围与存在
    assert model.rating is None or (0 <= model.rating <= 10)
    # 至少存在部分映射字段
    assert isinstance(model.genres, list)
    assert isinstance(model.metadata.country, list)
    # 语言可能含多项，插件取第一项或 None
    assert model.metadata.language is None or isinstance(model.metadata.language, str)


def test_integration_omdb_download_artwork_real(tmp_path):
    plugin = OMDBMetadataPlugin()
    ok = plugin.download_artwork(title="Arrival", dest_dir=str(tmp_path), release_date=date(2016, 11, 11))
    assert ok is True
    # 文件名由插件根据 URL 猜测扩展名，通常为 .jpg/.png
    possible = [Path(tmp_path) / "poster.jpg", Path(tmp_path) / "poster.png", Path(tmp_path) / "poster.webp"]
    saved = next((p for p in possible if p.exists()), None)
    assert saved is not None and saved.stat().st_size > 0


def test_integration_plugin_manager_fetch_prefer_omdb():
    mgr = PluginManager()
    mgr.scan_and_load()
    names = [p.name for p in mgr.get_by_type(PluginType.METADATA)]
    assert "omdb" in names

    result = mgr.fetch_movie_metadata(
        title="Arrival",
        release_date=date(2016, 11, 11),
        library_id="lib1",
        prefer="omdb",
    )
    assert result is not None
    assert isinstance(result, MovieCreate)
    assert result.title and result.library_id == "lib1"
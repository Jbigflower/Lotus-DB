import pytest
import requests
from datetime import date
from pathlib import Path

from src.plugins.providers.omdb import OMDBMetadataPlugin
from src.plugins.manager import PluginManager
from src.plugins.base_plugin import PluginType
from src.models import MovieCreate


class FakeResponse:
    def __init__(self, json_data=None, content=b"", status_code=200):
        self._json_data = json_data
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP error")

    def json(self):
        return self._json_data


@pytest.mark.asyncio
async def test_omdb_fetch_movie_metadata_maps_fields(monkeypatch):
    plugin = OMDBMetadataPlugin(api_key="TESTKEY")
    omdb_json = {
        "Response": "True",
        "Title": "Arrival",
        "Director": "Denis Villeneuve",
        "Actors": "Amy Adams, Jeremy Renner, Forest Whitaker",
        "Plot": "A linguist works with the military to communicate with alien lifeforms.",
        "Genre": "Drama, Sci-Fi",
        "Country": "USA, Canada",
        "Language": "English, Mandarin",
        "imdbRating": "7.9",
        "Released": "11 Nov 2016",
        "Year": "2016",
        "Runtime": "116 min",
        "Poster": "https://example.com/poster.jpg",
    }
    # 避免真实网络请求
    monkeypatch.setattr(plugin, "_fetch_by_title", lambda t, d: omdb_json)

    model = await plugin.fetch_movie_metadata(title="Arrival", release_date=date(2016, 11, 16), library_id="lib1")
    assert isinstance(model, MovieCreate)
    assert model.library_id == "lib1"
    assert model.title == "Arrival"
    assert model.directors == ["Denis Villeneuve"]
    assert model.actors[:2] == ["Amy Adams", "Jeremy Renner"]
    assert model.description.startswith("A linguist works")
    assert model.genres == ["Drama", "Sci-Fi"]
    assert model.metadata.country == ["USA", "Canada"]
    assert model.metadata.language == "English"  # 取第一语言
    assert model.rating == 7.9
    assert model.release_date == date(2016, 11, 11)  # 优先使用 Released
    assert model.metadata.duration == 116 * 60


@pytest.mark.asyncio
async def test_omdb_fetch_movie_metadata_handles_na(monkeypatch):
    plugin = OMDBMetadataPlugin(api_key="TESTKEY")
    omdb_json = {
        "Response": "True",
        "Title": "Unknown",
        "Director": "N/A",
        "Actors": "N/A",
        "Plot": "N/A",
        "Genre": "N/A",
        "Country": "N/A",
        "Language": "N/A",
        "imdbRating": "N/A",
        "Released": "N/A",
        "Runtime": "N/A",
    }
    monkeypatch.setattr(plugin, "_fetch_by_title", lambda t, d: omdb_json)

    model = await plugin.fetch_movie_metadata(title="Unknown", release_date=None, library_id="lib1")
    assert isinstance(model, MovieCreate)
    assert model.title == "Unknown"
    assert model.directors == []
    assert model.actors == []
    assert model.description == ""
    assert model.genres == []
    assert model.metadata.country == []
    assert model.metadata.language is None
    assert model.rating is None
    assert model.release_date is None
    assert model.metadata.duration is None


@pytest.mark.asyncio
async def test_omdb_download_artwork_saves_file(monkeypatch, tmp_path):
    plugin = OMDBMetadataPlugin(api_key="TESTKEY")
    omdb_json = {
        "Response": "True",
        "Poster": "https://images.example.com/poster.png",
    }
    monkeypatch.setattr(plugin, "_fetch_by_title", lambda t, d: omdb_json)

    def fake_get(url, *args, **kwargs):
        # 仅模拟海报文件下载
        if url.startswith("https://images.example.com/"):
            return FakeResponse(content=b"PNGDATA", status_code=200)
        return FakeResponse(json_data={"Response": "True"}, status_code=200)

    monkeypatch.setattr(requests, "get", fake_get)

    result = await plugin.download_artwork(title="Arrival", dest_dir=str(tmp_path))
    assert result["poster"] is not None
    saved = Path(tmp_path) / "poster.png"
    assert saved.exists() and saved.stat().st_size > 0


@pytest.mark.asyncio
async def test_omdb_download_actor_portrait_returns_false(tmp_path):
    plugin = OMDBMetadataPlugin(api_key="TESTKEY")
    ok = await plugin.download_actor_portrait(person_name="Amy Adams", dest_dir=str(tmp_path))
    assert ok is False


def test_plugin_manager_scans_and_registers_omdb():
    mgr = PluginManager()
    # 默认扫描 src/plugins/providers 路径
    mgr.scan_and_load()
    names = [p.name for p in mgr.get_by_type(PluginType.METADATA)]
    assert "omdb" in names

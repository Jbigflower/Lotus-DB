from __future__ import annotations

import os
import asyncio
from typing import List, Optional
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse
import requests

from config.logging import get_service_logger
from config.setting import settings
from src.plugins.base_plugin import MetadataPlugin
from src.models import MovieCreate, MovieMetadata

logger = get_service_logger("plugins.omdb")


class OMDBMetadataPlugin(MetadataPlugin):
    """
    OMDb 元数据插件
    - 基于 OMDb 标题检索（t + y），返回标准 MovieCreate
    - 下载海报（Poster 字段）到目标目录
    - 演员头像不支持（返回 False）
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://www.omdbapi.com/"):
        super().__init__(name="omdb", provider="OMDb", version="1.0.0")
        # 优先从 settings.plugins.omdb_api_key（若存在）读取，其次环境变量 OMDB_API_KEY
        self.api_key = api_key or getattr(getattr(settings, "plugins", object()), "omdb_api_key", None) or os.getenv("OMDB_API_KEY")
        self.base_url = base_url
        if not self.api_key:
            logger.warning("未配置 OMDB API KEY（settings.plugins.omdb_api_key 或环境变量 OMDB_API_KEY），插件将无法工作。")

    # ---------- MetadataPlugin 接口实现 ---------- #

    async def fetch_movie_metadata(
        self,
        title: str,
        library_id: str,
        release_date: Optional[date] = None,
    ) -> MovieCreate:
        results = await self.fetch_movies_metadata(
            [title],
            library_id,
            [release_date] if release_date is not None else None,
        )
        return results[0]

    async def download_artwork(
        self,
        title: str,
        dest_dir: str | Path,
        release_date: Optional[date] = None,
    ) -> dict[str, Optional[str]]:
        # 单个包装器：调用批量
        results = await self.download_artworks(
            [title],
            [dest_dir],
            [release_date] if release_date is not None else None,
        )
        return results[0]

    # 批量实现：元数据（并发执行）
    async def fetch_movies_metadata(
        self,
        titles: list[str],
        library_id: str,
        release_dates: Optional[list[Optional[date]]] = None,
    ) -> list[MovieCreate]:

        async def _build(title: str, release_date: Optional[date]) -> MovieCreate:
            data = await self._fetch_by_title_async(title, release_date)
            if not data:
                logger.info(f"OMDB 未找到影片: title={title}, release_date={release_date}")
                return MovieCreate(
                    library_id=library_id,
                    title=title,
                    title_cn="",
                    directors=[],
                    actors=[],
                    description="",
                    description_cn="",
                    release_date=release_date,
                    genres=[],
                    metadata=MovieMetadata(),
                    rating=None,
                    tags=[],
                )

            title_en = data.get("Title") or title
            directors = self._split_list_field(data.get("Director"))
            actors = self._split_list_field(data.get("Actors"))
            description = data.get("Plot") if (data.get("Plot") and data.get("Plot") != "N/A") else ""
            genres = self._split_list_field(data.get("Genre"))
            country = self._split_list_field(data.get("Country"))
            language_list = self._split_list_field(data.get("Language"))
            language = language_list[0] if language_list else None
            rating = self._parse_float(data.get("imdbRating"))
            release_dt = self._parse_release_date(data.get("Released")) or release_date or self._year_to_date(data.get("Year"))
            runtime_sec = self._parse_runtime_seconds(data.get("Runtime"))

            return MovieCreate(
                library_id=library_id,
                title=title_en,
                title_cn="",
                directors=directors,
                actors=actors,
                description=description,
                description_cn="",
                release_date=release_dt,
                genres=genres,
                metadata=MovieMetadata(duration=runtime_sec, country=country, language=language),
                rating=rating,
                tags=[],
            )

        tasks = []
        for i, t in enumerate(titles):
            rd = release_dates[i] if release_dates and i < len(release_dates) else None
            tasks.append(_build(t, rd))
        return await asyncio.gather(*tasks)

    # 批量实现：海报/背景/缩略图（并发执行）
    async def download_artworks(
        self,
        titles: list[str],
        dest_dirs: list[str | Path],
        release_dates: Optional[list[Optional[date]]] = None,
    ) -> list[dict[str, Optional[str]]]:
        async def _download_one(title: str, dest_dir: str | Path, release_date: Optional[date]) -> dict[str, Optional[str]]:
            poster_path: Optional[str] = None
            backdrop_path: Optional[str] = None
            thumbnail_path: Optional[str] = None

            data = await self._fetch_by_title_async(title, release_date)
            try:
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                if data and data.get("Poster") and data.get("Poster") != "N/A":
                    poster_url = data["Poster"]
                    ext = self._guess_ext_from_url_or_content(poster_url)
                    # poster
                    p_path = Path(dest_dir) / f"poster{ext}"
                    content = await self._download_bytes_async(poster_url, timeout=20)
                    if content:
                        await self._write_bytes_async(p_path, content)
                        poster_path = str(p_path.resolve())
                        # thumbnail（占位：与 poster 同内容）
                        t_path = Path(dest_dir) / "thumbnail.jpg"
                        await self._write_bytes_async(t_path, content)
                        thumbnail_path = str(t_path.resolve())
                        # OMDB 无 backdrop，返回 None（可在其他 Provider 中实现）
                        backdrop_path = None
                        logger.info(f"OMDB 海报资源已下载: poster={poster_path}, thumbnail={thumbnail_path}, backdrop=None")
                    else:
                        logger.info(f"OMDB 下载海报失败: title={title}, release_date={release_date}")
                else:
                    logger.info(f"OMDB 未提供海报: title={title}, release_date={release_date}")
            except Exception as e:
                logger.error(f"下载 OMDB 海报失败: title={title}", exc_info=e)

            return {"poster": poster_path, "backdrop": backdrop_path, "thumbnail": thumbnail_path}

        tasks = []
        for i, t in enumerate(titles):
            d = dest_dirs[i] if i < len(dest_dirs) else dest_dirs[-1]
            r = release_dates[i] if release_dates and i < len(release_dates) else None
            tasks.append(_download_one(t, d, r))
        return await asyncio.gather(*tasks)

    async def download_actor_portraits(
        self,
        person_names: list[str],
        dest_dirs: list[str | Path],
    ) -> list[bool]:
        # OMDb 不提供演员头像，批量返回全 False
        results: list[bool] = []
        for i, name in enumerate(person_names):
            dest = dest_dirs[i] if i < len(dest_dirs) else dest_dirs[-1]
            logger.info(f"OMDB 不支持演员头像下载: person={name}, dest_dir={dest}")
            results.append(False)
        return results

    # ---------- 内部工具方法（异步化封装） ---------- #
    async def _fetch_by_title_async(self, title: str, release_date: Optional[date]) -> Optional[dict]:
        if not self.api_key:
            return None
        params = {
            "apikey": self.api_key,
            "t": title,
            "plot": "full",
        }
        if release_date:
            params["y"] = str(release_date.year)
        try:
            data = await asyncio.to_thread(self._fetch_by_title, title, release_date)
            if data and data.get("Response") == "True":
                return data
            return None
        except Exception as e:
            logger.error(f"OMDB 请求失败: title={title}, year={params.get('y')}", exc_info=e)
            return None

    def _fetch_by_title(self, title: str, release_date: Optional[date]) -> Optional[dict]:
        params = {
            "apikey": self.api_key,
            "t": title,
            "plot": "full",
        }
        if release_date:
            params["y"] = str(release_date.year)
        return self._do_request_json(self.base_url, params, 15)

    def _do_request_json(self, url: str, params: dict, timeout: int) -> Optional[dict]:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    async def _download_bytes_async(self, url: str, timeout: int = 20) -> Optional[bytes]:
        try:
            return await asyncio.to_thread(self._download_bytes_sync, url, timeout)
        except Exception:
            return None

    def _download_bytes_sync(self, url: str, timeout: int = 20) -> Optional[bytes]:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content

    async def _write_bytes_async(self, path: Path, content: bytes) -> None:
        await asyncio.to_thread(self._write_bytes_sync, path, content)

    def _write_bytes_sync(self, path: Path, content: bytes) -> None:
        with open(path, "wb") as f:
            f.write(content)

    @staticmethod
    def _split_list_field(val: Optional[str]) -> List[str]:
        if not val or val == "N/A":
            return []
        return [s.strip() for s in val.split(",") if s.strip()]

    @staticmethod
    def _parse_float(val: Optional[str]) -> Optional[float]:
        if not val or val == "N/A":
            return None
        try:
            return float(val)
        except Exception:
            return None

    @staticmethod
    def _parse_release_date(val: Optional[str]) -> Optional[date]:
        """
        OMDb Released 样例：'16 Nov 2016' 或 'N/A'
        """
        if not val or val == "N/A":
            return None
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(val, fmt).date()
            except Exception:
                continue
        return None

    @staticmethod
    def _year_to_date(val: Optional[str]) -> Optional[date]:
        if not val or not val.isdigit():
            return None
        try:
            return date(int(val), 1, 1)
        except Exception:
            return None

    @staticmethod
    def _parse_runtime_seconds(val: Optional[str]) -> Optional[int]:
        """
        OMDb Runtime 样例：'123 min'
        """
        if not val or val == "N/A":
            return None
        try:
            minutes = int(val.split()[0])
            return minutes * 60
        except Exception:
            return None

    @staticmethod
    def _guess_ext_from_url_or_content(url: str) -> str:
        parsed = urlparse(url)
        name = Path(parsed.path).name
        if "." in name:
            ext = "." + name.split(".")[-1].lower()
            if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                return ext if ext != ".jpeg" else ".jpg"
        # 默认 jpg
        return ".jpg"


def get_plugins() -> List[MetadataPlugin]:
    # 允许通过 settings 或环境变量传入 API KEY
    api_key = getattr(getattr(settings, "plugins", object()), "omdb_api_key", None) or os.getenv("OMDB_API_KEY")
    return [OMDBMetadataPlugin(api_key=api_key)]

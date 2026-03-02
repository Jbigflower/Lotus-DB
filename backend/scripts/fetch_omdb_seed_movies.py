from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import requests

from src.models import MovieCreate, MovieMetadata
from src.plugins.providers.omdb import OMDBMetadataPlugin


@dataclass(frozen=True)
class MovieSpec:
    title_query: str
    year: Optional[int] = None
    title_cn: str = ""


def _ensure_out_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _omdb_request(base_url: str, api_key: str, params: dict[str, Any], timeout: int = 15) -> Optional[dict[str, Any]]:
    clean_params = {k: v for k, v in params.items() if v is not None}
    resp = requests.get(base_url, params={"apikey": api_key, **clean_params}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("Response") == "True":
        return data
    return None


def _omdb_fetch_best_effort(
    *,
    base_url: str,
    api_key: str,
    title: str,
    year: Optional[int],
) -> Optional[dict[str, Any]]:
    data = _omdb_request(base_url, api_key, {"t": title, "y": str(year) if year else None, "plot": "full"})
    if data:
        return data

    search_params: dict[str, Any] = {"s": title, "type": "movie"}
    if year:
        search_params["y"] = str(year)
    search = _omdb_request(base_url, api_key, search_params)
    if not search:
        return None

    items = search.get("Search")
    if not isinstance(items, list) or not items:
        return None

    imdb_id = items[0].get("imdbID")
    if not imdb_id:
        return None

    return _omdb_request(base_url, api_key, {"i": imdb_id, "plot": "full"})


def _build_fallback_model(*, library_id: str, title_query: str, year: Optional[int], title_cn: str) -> MovieCreate:
    rd = date(year, 1, 1) if year else None
    return MovieCreate(
        library_id=library_id,
        title=title_query,
        title_cn=title_cn,
        directors=[],
        actors=[],
        description="",
        description_cn="",
        release_date=rd,
        genres=[],
        metadata=MovieMetadata(),
        rating=None,
        tags=[],
    )


def _build_model_from_omdb(
    *,
    plugin: OMDBMetadataPlugin,
    library_id: str,
    title_query: str,
    year: Optional[int],
    title_cn: str,
    data: dict[str, Any],
) -> MovieCreate:
    directors = plugin._split_list_field(data.get("Director"))
    actors = plugin._split_list_field(data.get("Actors"))
    description = data.get("Plot") if (data.get("Plot") and data.get("Plot") != "N/A") else ""
    genres = plugin._split_list_field(data.get("Genre"))
    country = plugin._split_list_field(data.get("Country"))
    language_list = plugin._split_list_field(data.get("Language"))
    language = language_list[0] if language_list else None
    rating = plugin._parse_float(data.get("imdbRating"))

    rd_default = date(year, 1, 1) if year else None
    release_dt = plugin._parse_release_date(data.get("Released")) or rd_default or plugin._year_to_date(data.get("Year"))
    runtime_sec = plugin._parse_runtime_seconds(data.get("Runtime"))
    title_en = data.get("Title") or title_query

    return MovieCreate(
        library_id=library_id,
        title=title_en,
        title_cn=title_cn,
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


async def _fetch_one(
    *,
    plugin: OMDBMetadataPlugin,
    base_url: str,
    api_key: Optional[str],
    library_id: str,
    spec: MovieSpec,
    semaphore: asyncio.Semaphore,
) -> MovieCreate:
    async with semaphore:
        if not api_key:
            return _build_fallback_model(
                library_id=library_id,
                title_query=spec.title_query,
                year=spec.year,
                title_cn=spec.title_cn,
            )
        try:
            data = await asyncio.to_thread(
                _omdb_fetch_best_effort,
                base_url=base_url,
                api_key=api_key,
                title=spec.title_query,
                year=spec.year,
            )
            if not data:
                return _build_fallback_model(
                    library_id=library_id,
                    title_query=spec.title_query,
                    year=spec.year,
                    title_cn=spec.title_cn,
                )
            return _build_model_from_omdb(
                plugin=plugin,
                library_id=library_id,
                title_query=spec.title_query,
                year=spec.year,
                title_cn=spec.title_cn,
                data=data,
            )
        except Exception:
            return _build_fallback_model(
                library_id=library_id,
                title_query=spec.title_query,
                year=spec.year,
                title_cn=spec.title_cn,
            )


async def fetch_group(
    *,
    plugin: OMDBMetadataPlugin,
    base_url: str,
    api_key: Optional[str],
    library_id: str,
    specs: list[MovieSpec],
    concurrency: int,
) -> list[MovieCreate]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    tasks = [
        _fetch_one(
            plugin=plugin,
            base_url=base_url,
            api_key=api_key,
            library_id=library_id,
            spec=spec,
            semaphore=semaphore,
        )
        for spec in specs
    ]
    return await asyncio.gather(*tasks)


def _to_dumpable(models: list[MovieCreate]) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in models]


def _get_specs() -> dict[str, list[MovieSpec]]:
    oscar = [
        MovieSpec("American Beauty", 1999),
        MovieSpec("Gladiator", 2000),
        MovieSpec("A Beautiful Mind", 2001),
        MovieSpec("Chicago", 2002),
        MovieSpec("The Lord of the Rings: The Return of the King", 2003),
        MovieSpec("Million Dollar Baby", 2004),
        MovieSpec("Crash", 2004),
        MovieSpec("The Departed", 2006),
        MovieSpec("No Country for Old Men", 2007),
        MovieSpec("Slumdog Millionaire", 2008),
        MovieSpec("The Hurt Locker", 2008),
        MovieSpec("The King's Speech", 2010),
        MovieSpec("The Artist", 2011),
        MovieSpec("Argo", 2012),
        MovieSpec("12 Years a Slave", 2013),
        MovieSpec("Birdman", 2014),
        MovieSpec("Spotlight", 2015),
        MovieSpec("Moonlight", 2016),
        MovieSpec("The Shape of Water", 2017),
        MovieSpec("Green Book", 2018),
        MovieSpec("Parasite", 2019),
        MovieSpec("Nomadland", 2020),
        MovieSpec("CODA", 2021),
        MovieSpec("Everything Everywhere All at Once", 2022),
        MovieSpec("Oppenheimer", 2023),
    ]

    hong_kong = [
        MovieSpec("A Better Tomorrow", 1986, "英雄本色"),
        MovieSpec("A Chinese Odyssey", 1995, "大话西游"),
        MovieSpec("Infernal Affairs", 2002, "无间道"),
        MovieSpec("Days of Being Wild", 1990, "阿飞正传"),
        MovieSpec("Ashes of Time", 1994, "东邪西毒"),
        MovieSpec("Police Story", 1985, "警察故事"),
        MovieSpec("All for the Winner", 1990, "赌圣"),
        MovieSpec("A Chinese Ghost Story", 1987, "倩女幽魂"),
        MovieSpec("Kung Fu Hustle", 2004, "功夫"),
        MovieSpec("Flirting Scholar", 1993, "唐伯虎点秋香"),
    ]

    mainland = [
        MovieSpec("Farewell My Concubine", 1993, "霸王别姬"),
        MovieSpec("To Live", 1994, "活着"),
        MovieSpec("Red Sorghum", 1987, "红高粱"),
        MovieSpec("Let the Bullets Fly", 2010, "让子弹飞"),
        MovieSpec("Dying to Survive", 2018, "我不是药神"),
        MovieSpec("Wreaths at the Foot of the Mountain", 1984, "高山下的花环"),
        MovieSpec("Hibiscus Town", 1986, "芙蓉镇"),
        MovieSpec("Raise the Red Lantern", 1991, "大红灯笼高高挂"),
        MovieSpec("In the Heat of the Sun", 1994, "阳光灿烂的日子"),
        MovieSpec("The Wandering Earth", 2019, "流浪地球"),
    ]

    marvel = [
        MovieSpec("Iron Man", 2008),
        MovieSpec("The Incredible Hulk", 2008),
        MovieSpec("Iron Man 2", 2010),
        MovieSpec("Thor", 2011),
        MovieSpec("Captain America: The First Avenger", 2011),
        MovieSpec("The Avengers", 2012),
        MovieSpec("Iron Man 3", 2013),
        MovieSpec("Thor: The Dark World", 2013),
        MovieSpec("Captain America: The Winter Soldier", 2014),
        MovieSpec("Guardians of the Galaxy", 2014),
        MovieSpec("Avengers: Age of Ultron", 2015),
        MovieSpec("Ant-Man", 2015),
        MovieSpec("Captain America: Civil War", 2016),
    ]

    comedy = [
        MovieSpec("Flirting Scholar", 1993, "唐伯虎点秋香"),
        MovieSpec("A Chinese Odyssey", 1995, "大话西游"),
        MovieSpec("The God of Cookery", 1996, "食神"),
        MovieSpec("From Beijing with Love", 1994, "国产凌凌漆"),
        MovieSpec("Kung Fu Hustle", 2004, "功夫"),
        MovieSpec("Let the Bullets Fly", 2010, "让子弹飞"),
        MovieSpec("Dying to Survive", 2018, "我不是药神"),
        MovieSpec("Crazy Stone", 2006, "疯狂的石头"),
        MovieSpec("Goodbye Mr. Loser", 2015, "夏洛特烦恼"),
        MovieSpec("Hello Mr. Billionaire", 2018, "西虹市首富"),
    ]

    return {
        "oscar_best_picture_2000_2024": oscar,
        "hong_kong_classics_10": hong_kong,
        "mainland_classics_10": mainland,
        "marvel_13": marvel,
        "comedy_10": comedy,
    }


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data/test_data")
    parser.add_argument("--library-id", default="lib_placeholder")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--base-url", default="https://www.omdbapi.com/")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out_dir = (repo_root / args.out_dir).resolve()
    _ensure_out_dir(out_dir)

    plugin = OMDBMetadataPlugin(api_key=os.getenv("OMDB_API_KEY"), base_url=args.base_url)
    api_key = plugin.api_key

    groups = _get_specs()
    for name, specs in groups.items():
        models = await fetch_group(
            plugin=plugin,
            base_url=args.base_url,
            api_key=api_key,
            library_id=args.library_id,
            specs=specs,
            concurrency=args.concurrency,
        )
        out_path = out_dir / f"{name}.json"
        _write_json(out_path, _to_dumpable(models))

    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

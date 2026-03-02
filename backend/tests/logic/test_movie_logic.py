import pytest
from typing import Any, Dict, Optional, List
from bson import ObjectId
from datetime import datetime, timezone

from src.logic.movies.movie_logic import MovieLogic
from src.models import MovieCreate, MovieInDB, MovieRead, MovieUpdate, MoviePageResult

from src.core.exceptions import ConflictError

# --------- Fake Cache ---------
class FakeMovieCache:
    def __init__(self):
        self.details = {}
        self.search_pages = {}

    async def get_detail(self, item_id: str): return self.details.get(item_id)
    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None):
        if item.get("id"): self.details[item["id"]] = item; return True
        return False
    async def delete_search_cache_all(self): self.search_pages.clear(); return True
    async def get_search_page(self, key: str, page: int): return self.search_pages.get(key, {}).get(page)
    async def cache_search_page(self, key: str, page: int, payload: Dict[str, Any]): self.search_pages.setdefault(key, {})[page] = payload

# --------- Fake Repo ---------
class FakeMovieRepo:
    def __init__(self):
        self.store: Dict[str, MovieInDB] = {}
        self.last_filter: Optional[Dict[str, Any]] = None

    async def exists(self, filter_dict: Dict[str, Any], session=None) -> bool:
        # match title+release_date+library_id
        def key(m: MovieInDB):
            return (m.title, m.model_dump().get("release_date"), ObjectId(m.library_id))
        k = (filter_dict["title"], filter_dict["release_date"], filter_dict["library_id"])
        return any(key(v) == k for v in self.store.values())

    async def insert_one(self, payload: MovieCreate, session=None) -> MovieInDB:
        _id = str(ObjectId())
        in_db = MovieInDB(
            id=_id,
            library_id=payload.library_id,
            title=payload.title,
            title_cn=payload.title_cn,
            directors=payload.directors,
            actors=payload.actors,
            description=payload.description,
            description_cn=payload.description_cn,
            release_date=payload.release_date,
            genres=payload.genres,
            metadata=payload.metadata,
            rating=payload.rating,
            tags=payload.tags,
            has_poster=False,
            has_backdrop=False,
            has_thumbnail=False,
            is_deleted=False,
            deleted_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.store[_id] = in_db
        return in_db

    async def find(self, filter_dict: Dict[str, Any], skip: int = 0, limit: int = 20, sort=None, session=None):
        self.last_filter = filter_dict
        def match(item: MovieInDB):
            ok = True
            if "library_id" in filter_dict:
                ok = ok and ObjectId(item.library_id) == filter_dict["library_id"]
            if "genres" in filter_dict and "$in" in filter_dict["genres"]:
                ok = ok and any(g in item.genres for g in filter_dict["genres"]["$in"])
            if "rating" in filter_dict:
                cond = filter_dict["rating"]
                val = item.rating or 0
                if "$gte" in cond: ok = ok and val >= cond["$gte"]
                if "$lte" in cond: ok = ok and val <= cond["$lte"]
            return ok
        items = [v for v in self.store.values() if match(v)]
        return items[skip: skip + limit]

    async def count(self, filter_dict: Dict[str, Any], session=None):
        return len(await self.find(filter_dict, 0, 10**9, session=session))

# --------- Tests ---------
@pytest.mark.asyncio
async def test_create_movie_conflict():
    logic = MovieLogic()
    logic.repo = FakeMovieRepo()
    logic.cache_repo = FakeMovieCache()

    mv = MovieCreate(
        library_id=str(ObjectId()),
        title="T",
        title_cn="TT",
        directors=[],
        actors=[],
        description="",
        description_cn="",
        release_date=None,
        genres=[],
        metadata={},
        rating=8.0,
        tags=[],
    )
    # insert once to cause conflict
    await logic.repo.insert_one(mv)
    with pytest.raises(ConflictError):
        await logic.create_movie(mv)

@pytest.mark.asyncio
async def test_list_movies_filter_and_cache_miss_fill():
    logic = MovieLogic()
    logic.repo = FakeMovieRepo()
    logic.cache_repo = FakeMovieCache()

    lib_id = str(ObjectId())
    m1 = await logic.repo.insert_one(MovieCreate(
        library_id=lib_id,
        title="A",
        title_cn="AC",
        directors=[],
        actors=[],
        description="",
        description_cn="",
        release_date=None,
        genres=["action"],
        metadata={},
        rating=8.5,
        tags=[],
    ))
    m2 = await logic.repo.insert_one(MovieCreate(
        library_id=lib_id,
        title="B",
        title_cn="BC",
        directors=[],
        actors=[],
        description="",
        description_cn="",
        release_date=None,
        genres=["drama"],
        metadata={},
        rating=5.0,
        tags=[],
    ))

    page = await logic.list_movies(
        query=None,
        genres=["action"],
        min_rating=8.0,
        max_rating=None,
        start_date=None,
        end_date=None,
        tags=None,
        library_id=lib_id,
        page=1,
        size=20,
    )
    assert isinstance(page, MoviePageResult)
    assert page.total == 1
    # library_id filter uses ObjectId
    assert isinstance(logic.repo.last_filter["library_id"], ObjectId)
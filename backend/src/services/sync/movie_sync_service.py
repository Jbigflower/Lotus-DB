from src.db.mongo_db import get_movies_collection
from src.models import MovieInDB
from src.repos import MovieEmbeddingRepo
from .base_sync_service import BaseSyncService


class MovieSyncService(BaseSyncService[MovieInDB]):
    """电影集合 → LanceDB 同步服务"""

    TEXT_FIELDS = [
        "title",
        "title_cn",
        "description",
        "description_cn",
        "genres",
        "directors",
        "actors",
        "tags",
        "rating",
        "release_date",
    ]

    def get_collection(self):
        return get_movies_collection()

    def get_target_repo(self):
        return MovieEmbeddingRepo()

    def to_model_in_db(self, doc):
        return MovieInDB(
            id=str(doc.get("_id")),
            library_id=str(doc.get("library_id")),
            title=doc.get("title"),
            title_cn=doc.get("title_cn", ""),
            description=doc.get("description", ""),
            description_cn=doc.get("description_cn", ""),
            genres=(doc.get("genres") or []) or [],
            directors=(doc.get("directors") or []) or [],
            actors=(doc.get("actors") or []) or [],
            tags=(doc.get("tags") or []) or [],
            rating=doc.get("rating", 0) or 0,
            release_date=doc.get("release_date"),
            is_deleted=bool(doc.get("is_deleted", False)),
            metadata=(doc.get("metadata") or {}) or {},
        )

    def build_text(self, m: MovieInDB) -> str:
        # 将关键信息拼接为快照文本以减少无意义更新
        parts = [
            m.title or "",
            m.title_cn or "",
            m.description or "",
            m.description_cn or "",
            ",".join(m.genres or []),
            ",".join(m.directors or []),
            ",".join(m.actors or []),
            ",".join(m.tags or []),
            str(m.rating or 0),
            str(m.release_date or ""),
        ]
        return "\n".join(parts)

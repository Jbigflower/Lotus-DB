# src/services/sync/subtitle_sync_service.py
from typing import Any, Dict
from pydantic import BaseModel
from src.models import AssetInDB
from src.db import get_assets_collection
from src.repos import SubtitleEmbeddingRepo
from .base_sync_service import BaseSyncService
from config.logging import get_service_logger

logger = get_service_logger("subtitle_sync_service")


class SubtitleSyncModel(BaseModel):
    id: str
    movie_id: str
    content: str
    start_time: float = 0.0
    end_time: float = 0.0
    language: str = "unknown"
    is_deleted: bool = False


class SubtitleSyncService(BaseSyncService[SubtitleSyncModel]):
    """同步字幕到 LanceDB"""

    def get_collection(self):
        return get_assets_collection()

    def get_target_repo(self):
        return SubtitleEmbeddingRepo()

    def to_model_in_db(self, doc: Dict[str, Any]) -> SubtitleSyncModel:
        metadata = doc.get("metadata") or {}
        content = doc.get("text") or doc.get("content") or doc.get("description") or ""
        return SubtitleSyncModel(
            id=str(doc["_id"]),
            movie_id=str(doc.get("movie_id", "")),
            content=content,
            start_time=float(doc.get("start_time") or 0.0),
            end_time=float(doc.get("end_time") or 0.0),
            language=doc.get("language") or metadata.get("language") or "unknown",
            is_deleted=bool(doc.get("is_deleted", False)),
        )

    def build_text(self, s: SubtitleSyncModel) -> str:
        return f"[{s.language}] {s.content or ''}"

# src/services/sync/note_sync_service.py
from typing import Any, Dict
from src.models import NoteInDB
from src.db import get_user_assets_collection
from src.repos import NoteEmbeddingRepo
from .base_sync_service import BaseSyncService
from config.logging import get_service_logger

logger = get_service_logger("note_sync_service")


class NoteSyncService(BaseSyncService[NoteInDB]):
    """同步笔记到 LanceDB"""

    def get_collection(self):
        return get_user_assets_collection()

    def get_target_repo(self):
        return NoteEmbeddingRepo()

    def to_model_in_db(self, doc: Dict[str, Any]) -> NoteInDB:
        return NoteInDB(
            id=str(doc["_id"]),
            user_id=str(doc.get("user_id")),
            movie_id=str(doc.get("movie_id")),
            type=doc.get("type", "note"),
            name=doc.get("name") or doc.get("title") or "untitled",
            path=doc.get("path") or "unknown",
            store_type=doc.get("store_type") or "local",
            related_movie_ids=doc.get("related_movie_ids", []) or [],
            content=doc.get("content", ""),
            tags=doc.get("tags", []) or [],
            is_deleted=bool(doc.get("is_deleted", False)),
        )

    def build_text(self, note: NoteInDB) -> str:
        # 标准化快照文本，减少无意义更新
        return f"{note.name or ''}\n{note.content or ''}\n{','.join(note.tags or [])}"

    async def _handle_change(self, change: Dict[str, Any], repo) -> None:
        op = change.get("operationType")
        if op == "delete":
            _id = str(change["documentKey"]["_id"])
            if hasattr(repo, "delete_by_parent_ids"):
                await repo.delete_by_parent_ids([_id], soft=False)
            else:
                await repo.delete([_id], soft=False)
            logger.info("[%s] 硬删除笔记: %s", self.__class__.__name__, _id)
            return
        doc = change.get("fullDocument") or {}
        model = self.to_model_in_db(doc)
        if getattr(model, "is_deleted", False):
            if hasattr(repo, "delete_by_parent_ids"):
                await repo.delete_by_parent_ids([model.id], soft=True)
            else:
                await repo.delete([model.id], soft=True)
            logger.info("[%s] 笔记被标记删除: %s", self.__class__.__name__, model.id)
            return
        text = self.build_text(model)
        if text is not None:
            old_text = None
            if hasattr(repo, "get_text_snapshot"):
                try:
                    old_text = await repo.get_text_snapshot(model.id)
                except Exception:
                    old_text = None
            if op == "update" and old_text == text:
                logger.debug(
                    "[%s] 文档 %s 文本未变化，跳过同步",
                    self.__class__.__name__,
                    model.id,
                )
                return
            await self._safe_upsert(repo, model)
            if hasattr(repo, "save_text_snapshot"):
                try:
                    await repo.save_text_snapshot(model.id, text)
                except Exception as e:
                    logger.warning("[%s] 保存快照失败: %s", self.__class__.__name__, e)
            return
        await self._safe_upsert(repo, model)

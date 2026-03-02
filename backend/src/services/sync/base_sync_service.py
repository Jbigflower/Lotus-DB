import asyncio
from typing import Dict, Any, List, Optional, TypeVar, Generic, Callable
from src.core.handler import service_handler
from config.logging import get_service_logger

logger = get_service_logger("sync_base_service")
TModel = TypeVar("TModel")


class BaseSyncService(Generic[TModel]):
    """
    通用的 Mongo → 目标存储 同步基类
    子类需实现:
        - get_collection()
        - to_model_in_db(doc)
        - get_target_repo()
    """

    TEXT_FIELDS: List[str] = []

    def __init__(self) -> None:
        self._tasks: List[asyncio.Task] = []
        self._stopping = asyncio.Event()

    @service_handler(action="start_sync_service")
    async def start(self) -> None:
        self._stopping.clear()
        task = asyncio.create_task(
            self._watch_collection(), name=f"watch_{self.__class__.__name__}"
        )
        self._tasks.append(task)
        logger.info("[%s] 同步服务已启动", self.__class__.__name__)

    @service_handler(action="stop_sync_service")
    async def stop(self) -> None:
        self._stopping.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        logger.info("[%s] 同步服务已停止", self.__class__.__name__)

    async def _watch_collection(self) -> None:
        """
        监听 MongoDB 集合变更
        """
        try:
            print(f"DEBUG: [{self.__class__.__name__}] _watch_collection started")
            coll = self.get_collection()
            repo = self.get_target_repo()
            print(f"DEBUG: [{self.__class__.__name__}] Got collection: {coll.name}")
            
            # 监听操作类型：插入、更新、替换、删除
            pipeline = [
                {"$match": {"operationType": {"$in": ["insert", "update", "replace", "delete"]}}}
            ]

            logger.info(f"[{self.__class__.__name__}] Starting watch on collection: {coll.name}")
            print(f"DEBUG: [{self.__class__.__name__}] Starting watch on collection: {coll.name}")
            # full_document="updateLookup" 保证 update 操作也能拿到完整文档
            async with coll.watch(pipeline, full_document="updateLookup") as stream:
                print(f"DEBUG: [{self.__class__.__name__}] Watch stream established")
                async for change in stream:
                    print(f"DEBUG: [{self.__class__.__name__}] Received change: {change.get('operationType')}")
                    logger.info(f"[{self.__class__.__name__}] Received change: {change.get('operationType')}")
                    if self._stopping.is_set():
                        break
                    
                    try:
                        await self._handle_change(change, repo)
                    except Exception as e:
                        logger.error(f"[{self.__class__.__name__}] Error handling change: {e}", exc_info=True)
                        print(f"DEBUG: [{self.__class__.__name__}] Error handling change: {e}")

        except Exception as e:
            if not self._stopping.is_set():
                logger.error(f"[{self.__class__.__name__}] 监听异常: {e}", exc_info=True)
                print(f"DEBUG: [{self.__class__.__name__}] Watch exception: {e}")

    async def _handle_change(self, change: Dict[str, Any], repo) -> None:
        op = change.get("operationType")
        logger.info(f"[{self.__class__.__name__}] Processing change: {op}")
        if op == "delete":
            _id = str(change["documentKey"]["_id"])
            if hasattr(repo, "delete_by_parent_ids"):
                await repo.delete_by_parent_ids([_id], soft=False)
                logger.info("[%s] 硬删除文档(父ID): %s", self.__class__.__name__, _id)
            else:
                await repo.delete([_id], soft=False)
                logger.info("[%s] 硬删除文档: %s", self.__class__.__name__, _id)
            return
        doc = change.get("fullDocument") or {}
        model = self.to_model_in_db(doc)
        if getattr(model, "is_deleted", False):
            if hasattr(repo, "delete_by_parent_ids"):
                await repo.delete_by_parent_ids([model.id], soft=True)
                logger.info(
                    "[%s] 文档被标记删除(父ID): %s", self.__class__.__name__, model.id
                )
            else:
                await repo.delete([model.id], soft=True)
                logger.info("[%s] 文档被标记删除: %s", self.__class__.__name__, model.id)
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
            logger.info(f"[{self.__class__.__name__}] Upserting model: {model.id}")
            await self._safe_upsert(repo, model)
            if hasattr(repo, "save_text_snapshot"):
                try:
                    await repo.save_text_snapshot(model.id, text)
                except Exception as e:
                    logger.warning("[%s] 保存快照失败: %s", self.__class__.__name__, e)
            return
        if op == "update" and (not self._has_semantic_change(change)):
            logger.debug(
                "[%s] 文档 %s 无文本字段变化，跳过同步",
                self.__class__.__name__,
                model.id,
            )
            return
        await self._safe_upsert(repo, model)

    async def _safe_upsert(self, repo, model: TModel, retries: int = 3) -> None:
        for attempt in range(retries):
            try:
                await repo.upsert([model])
                logger.info("[%s] 同步/更新成功: %s", self.__class__.__name__, model.id)
                return
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(
                        "[%s] 更新失败(%d/%d)，重试中: %s",
                        self.__class__.__name__,
                        attempt + 1,
                        retries,
                        e,
                    )
                    await asyncio.sleep(1.5)
                else:
                    logger.error(
                        "[%s] 更新失败，放弃重试: %s", self.__class__.__name__, e
                    )

    def _has_semantic_change(self, change: Dict[str, Any]) -> bool:
        updated_fields = (
            change.get("updateDescription", {}).get("updatedFields", {}) or {}
        )
        if not self.TEXT_FIELDS:
            return True
        for field in self.TEXT_FIELDS:
            if any((f.startswith(field) for f in updated_fields.keys())):
                return True
        return False

    def build_text(self, model: TModel) -> Optional[str]:
        """
        子类可重写：返回用于快照比对的文本
        返回 None 表示使用 TEXT_FIELDS 检测。
        """
        return None

    def get_collection(self):
        raise NotImplementedError

    def to_model_in_db(self, doc: Dict[str, Any]) -> TModel:
        raise NotImplementedError

    def get_target_repo(self):
        raise NotImplementedError

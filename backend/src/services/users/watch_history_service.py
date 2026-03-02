from typing import Optional, List, Dict, Any
from src.logic.users.watch_history_logic import WatchHistoryLogic
from src.logic.movies.asset_logic import MovieAssetLogic
from src.models import WatchHistoryPageResult, WatchHistoryRead, WatchHistoryUpdate, WatchHistoryCreate, WatchType, UserRole
from src.core.exceptions import ForbiddenError, ValidationError
from src.core.handler import service_handler
from config.logging import get_service_logger


class WatchHistoryService:
    """
    观看历史服务层
    - 权限校验、异常转换（业务异常）
    - 委托逻辑层执行核心业务
    """

    def __init__(self) -> None:
        self.logic = WatchHistoryLogic()
        self.asset_logic = MovieAssetLogic()
        self.logger = get_service_logger("watch_history_service")

    def _ensure_self_or_admin(self, target_user_id: str, current_user) -> None:
        is_admin = getattr(current_user, "role", None) == UserRole.ADMIN
        is_self = str(current_user.id) == str(target_user_id)
        if not is_admin and not is_self:
            raise ForbiddenError("无权限")

    @service_handler(action="list_user_watch_histories")
    async def list_user_watch_histories(
        self,
        current_user,
        watch_type: Optional[WatchType] = None,
        completed: Optional[bool] = None,
        page: int = 1,
        size: int = 20,
    ) -> WatchHistoryPageResult:
        return await self.logic.get_user_watch_histories(
            user_id=str(current_user.id),
            watch_type=watch_type,
            finished=completed,
            page=page,
            size=size,
        )

    @service_handler(action="update_watch_history_by_id")
    async def update_watch_history_by_id(self, watch_history_id: str, data: WatchHistoryUpdate, current_user) -> WatchHistoryRead:
        watch_history = await self.logic.get_watch_history(watch_history_id=watch_history_id)
        self._ensure_self_or_admin(target_user_id=watch_history.user_id, current_user=current_user)
        return await self.logic.update_watch_history(watch_history_id=watch_history_id, watch_history_update=data)

    @service_handler(action="get_watch_statistics")
    async def get_watch_statistics(self, current_user) -> Dict[str, Any]:
        return await self.logic.get_watch_statistics(user_id=str(current_user.id))

    @service_handler(action="get_recent_records")
    async def get_recent_watch_histories(
        self, current_user, limit: Optional[int] = None
    ) -> List[WatchHistoryRead]:
        result = await self.logic.get_recent_watch_histories(
            user_id=str(current_user.id), limit=100
        )
        return result[:limit] if limit and limit < 100 else result

    @service_handler(action="delete_watch_histories")
    async def delete_watch_histories(
        self, watch_history_ids: List[str], current_user
    ) -> int:
        watch_histories = await self.logic.get_watch_histories(watch_history_ids)
        for wc in watch_histories:
            self._ensure_self_or_admin(target_user_id=wc.user_id, current_user=current_user)
        return await self.logic.delete_watch_historise(watch_history_ids, current_user.id)

    @service_handler(action="list_user_asset_watch_histories")
    async def list_user_asset_watch_histories(self, asset_id: str, asset_type: WatchType, current_user) -> WatchHistoryRead:
        return await self.logic.get_by_asset(user_id=str(current_user.id), asset_id=str(asset_id), asset_type=asset_type)

    @service_handler(action="get_watch_history_by_id")
    async def get_watch_history_by_id(self, watch_history_id: str, current_user) -> WatchHistoryRead:
        watch_history = await self.logic.get_watch_history(watch_history_id=watch_history_id)
        self._ensure_self_or_admin(target_user_id=watch_history.user_id, current_user=current_user)
        return watch_history

    @service_handler(action="create_watch_history")
    async def create_watch_history(self, payload: WatchHistoryCreate, current_user) -> WatchHistoryRead:
        create_payload = WatchHistoryCreate(**{
            **payload.model_dump(exclude={"user_id"}),
            "user_id": str(current_user.id),
        })
        if not create_payload.total_duration or create_payload.total_duration == 0:
            try:
                asset = await self.asset_logic.get_asset(create_payload.asset_id)
                duration = getattr(getattr(asset, "metadata", None), "duration", None)
                if isinstance(duration, int) and duration > 0:
                    create_payload.total_duration = duration
            except Exception:
                pass
        return await self.logic.create_watch_history(payload=create_payload)

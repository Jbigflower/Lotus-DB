from src.services.sync.movie_sync_service import MovieSyncService
from src.services.sync.note_sync_service import NoteSyncService
from src.services.sync.subtitle_sync_service import SubtitleSyncService
from config.logging import get_logger

logger = get_logger("sync_manager")

class SyncManager:
    def __init__(self):
        self.movie_sync = MovieSyncService()
        self.note_sync = NoteSyncService()
        self.subtitle_sync = SubtitleSyncService()

    async def start_all(self):
        logger.info("正在启动所有同步服务...")
        await self.movie_sync.start()
        await self.note_sync.start()
        await self.subtitle_sync.start()
        logger.info("所有同步服务启动完成")

    async def stop_all(self):
        logger.info("正在停止所有同步服务...")
        await self.movie_sync.stop()
        await self.note_sync.stop()
        await self.subtitle_sync.stop()
        logger.info("所有同步服务停止完成")

sync_manager = SyncManager()

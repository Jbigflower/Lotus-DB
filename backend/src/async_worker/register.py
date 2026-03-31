from src.async_worker.core import TaskPriority
from src.models import TaskSubType

# 任务实现函数导入
from src.async_worker.tasks import (
    sync_dirty_collections_task,
    refresh_collection_cache_task,
    refactor_library_structure_task,
    cleanup_library_files_task,
    extract_metadata_task,
    generate_thumb_sprite_task,
    extract_memory_task,
    import_movies_task,
    download_movie_thumb_task,
    download_actor_thumb_task,
    download_subtitle_task,
)


# 统一任务注册表：消费者根据 name 查找函数并执行
TASK_REGISTRY = {
    TaskSubType.SYNC_DIRTY_COLLECTIONS: sync_dirty_collections_task,
    TaskSubType.REFRESH_COLLECTION_CACHE: refresh_collection_cache_task,
    TaskSubType.REFACTOR_LIBRARY_STRUCTURE: refactor_library_structure_task,
    TaskSubType.CLEANUP_LIBRARY_FILES: cleanup_library_files_task,
    TaskSubType.EXTRACT_METADATA: extract_metadata_task,
    TaskSubType.THUMB_SPRITE_GENERATE: generate_thumb_sprite_task,
    TaskSubType.MEMORY_EXTRACTION: extract_memory_task,
    TaskSubType.MOVIE_IMPORT: import_movies_task,
    TaskSubType.DOWNLOAD_MOVIE_FILE: download_movie_thumb_task,
    TaskSubType.DOWNLOAD_ACTOR_FILE: download_actor_thumb_task,
    TaskSubType.DOWNLOAD_SUBTITLE_FILE: download_subtitle_task,
}

# 定时投递的任务（由 Beat 投递）
SCHEDULED_TASKS = [
    # {
    #     "name": TaskSubType.SYNC_DIRTY_COLLECTIONS,
    #     "interval": 60,
    #     "priority": TaskPriority.HIGH,
    # },
]

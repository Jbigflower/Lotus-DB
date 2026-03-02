from typing import Dict, Any
from datetime import datetime, timezone
from src.logic import CollectionLogic
from src.core.handler import task_handler


@task_handler("同步脏集合")
async def sync_dirty_collections_task() -> Dict[str, Any]:
    logic = CollectionLogic()
    stats: Dict[str, Any] = {"start_time": datetime.now(timezone.utc).isoformat()}
    try:
        result = await logic.sync_dirty_collections_from_cache()
        stats.update(result)
        stats["status"] = "success"
    except Exception as e:
        stats["status"] = "failed"
        stats["error"] = str(e)
    finally:
        stats["end_time"] = datetime.now(timezone.utc).isoformat()
    return stats


@task_handler("刷新集合缓存")
async def refresh_collection_cache_task(user_id: str) -> Dict[str, Any]:
    logic = CollectionLogic()
    try:
        # 强制从 DB 获取并刷新缓存
        user_lists = await logic.get_user_collections(user_id, use_cache=False)
        
        return {
            "status": "success",
            "lists_count": len(user_lists),
            "action": "refreshed_cache",
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}

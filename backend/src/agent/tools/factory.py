from .library_tools import create_library_tool, get_library_tool, list_libraries_tool, delete_library_tool, restore_library_tool
from .movie_tools import (
    list_movies_tool,
    get_movie_tool,
    create_movie_tool,
    update_movies_by_ids_tool,
    delete_movies_by_ids_tool,
    restore_movies_by_ids_tool,
)
from .asset_tools import (
    list_movie_assets_page_tool,
    upload_movie_asset_tool,
    update_movie_asset_tool,
    delete_movie_assets_tool,
    restore_movie_assets_tool,
    list_recycle_bin_assets_tool,
    list_asset_thumbnails_signed_tool,
    get_movie_asset_tool,
)
from .user_asset_tools import (
    list_user_assets_tool,
    get_user_asset_tool,
    upload_user_asset_tool,
    create_text_user_asset_tool,
    update_user_asset_tool,
    delete_user_assets_tool,
    restore_user_assets_tool,
    list_isolated_user_assets_tool,
    list_user_asset_thumbnails_signed_tool,
)
from .collection_tools import (
    list_collections_tool,
    get_collection_tool,
    create_collection_tool,
    update_collection_tool,
    delete_collection_tool,
    add_movies_to_collection_tool,
    remove_movies_from_collection_tool,
    get_collection_movies_tool,
    init_user_default_collections_tool,
)
from .search_tools import (
    global_search_tool,
    ns_search_tool,
)
from .watch_history_tools import (
    list_user_watch_histories_tool,
    get_watch_history_by_id_tool,
    create_watch_history_tool,
    update_watch_history_by_id_tool,
    delete_watch_histories_tool,
    get_recent_watch_histories_tool,
    get_watch_statistics_tool,
    list_user_asset_watch_histories_tool,
)
from .task_tools import (
    list_tasks_tool,
    get_task_detail_tool,
    cancel_task_tool,
    get_task_progress_tool,
    retry_task_tool,
    delete_task_tool,
)
from .external_data_tools import (
    ddg_search_tool,
    omdb_search_tool,
    omdb_get_tool,
)

class ToolFactory:
    _all_tools = {
        "create_library": create_library_tool,
        "get_library": get_library_tool,
        "list_libraries": list_libraries_tool,
        "delete_library": delete_library_tool,
        "restore_library": restore_library_tool,
        # movies
        "list_movies": list_movies_tool,
        "get_movie": get_movie_tool,
        "create_movie": create_movie_tool,
        "update_movies_by_ids": update_movies_by_ids_tool,
        "delete_movies_by_ids": delete_movies_by_ids_tool,
        "restore_movies_by_ids": restore_movies_by_ids_tool,
        # movie assets
        "list_movie_assets_page": list_movie_assets_page_tool,
        "upload_movie_asset": upload_movie_asset_tool,
        "update_movie_asset": update_movie_asset_tool,
        "delete_movie_assets": delete_movie_assets_tool,
        "restore_movie_assets": restore_movie_assets_tool,
        "list_recycle_bin_assets": list_recycle_bin_assets_tool,
        "list_asset_thumbnails_signed": list_asset_thumbnails_signed_tool,
        "get_movie_asset": get_movie_asset_tool,
        # user assets
        "list_user_assets": list_user_assets_tool,
        "get_user_asset": get_user_asset_tool,
        "upload_user_asset": upload_user_asset_tool,
        "create_text_user_asset": create_text_user_asset_tool,
        "update_user_asset": update_user_asset_tool,
        "delete_user_assets": delete_user_assets_tool,
        "restore_user_assets": restore_user_assets_tool,
        "list_isolated_user_assets": list_isolated_user_assets_tool,
        "list_user_asset_thumbnails_signed": list_user_asset_thumbnails_signed_tool,
        # collections
        "list_collections": list_collections_tool,
        "get_collection": get_collection_tool,
        "create_collection": create_collection_tool,
        "update_collection": update_collection_tool,
        "delete_collection": delete_collection_tool,
        "add_movies_to_collection": add_movies_to_collection_tool,
        "remove_movies_from_collection": remove_movies_from_collection_tool,
        "get_collection_movies": get_collection_movies_tool,
        "init_user_default_collections": init_user_default_collections_tool,
        # search
        "global_search": global_search_tool,
        "ns_search": ns_search_tool,
        # watch history
        "list_user_watch_histories": list_user_watch_histories_tool,
        "get_watch_history_by_id": get_watch_history_by_id_tool,
        "create_watch_history": create_watch_history_tool,
        "update_watch_history_by_id": update_watch_history_by_id_tool,
        "delete_watch_histories": delete_watch_histories_tool,
        "get_recent_watch_histories": get_recent_watch_histories_tool,
        "get_watch_statistics": get_watch_statistics_tool,
        "list_user_asset_watch_histories": list_user_asset_watch_histories_tool,
        # tasks
        "list_tasks": list_tasks_tool,
        "get_task_detail": get_task_detail_tool,
        "cancel_task": cancel_task_tool,
        "get_task_progress": get_task_progress_tool,
        "retry_task": retry_task_tool,
        "delete_task": delete_task_tool,
        # external data
        "ddg_search": ddg_search_tool,
        "omdb_search": omdb_search_tool,
        "omdb_get": omdb_get_tool,
    }

    @classmethod
    def get_tools_for_agent(cls, agent_type: str):
        """根据 Agent 类型返回特定工具集"""
        # Define all tools list once
        all_tools_list = list(cls._all_tools.keys())
        
        mapping = {
            "simple_react": all_tools_list,  # Give all tools to React base
            "db_expert": all_tools_list,     # Give all tools to React Augment
            "orchestrator": [
                "create_library", "get_library", "list_libraries", "delete_library", "restore_library",
                "global_search", "ns_search",
                "ddg_search", "omdb_search", "omdb_get",
                "list_tasks", "get_task_detail", "get_task_progress", "cancel_task", "retry_task", "delete_task",
            ]
        }
        return [cls._all_tools[name] for name in mapping.get(agent_type, [])]

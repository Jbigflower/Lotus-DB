from typing import Dict, Any, List, Optional
from src.core.handler import task_handler
from src.logic import MovieLogic, TaskLogic
from src.plugins.manager import PluginManager

task_logic = TaskLogic()
movie_logic = MovieLogic()
plugin_manager = PluginManager()


@task_handler("下载指定电影的缩略图")
async def download_movie_thumb_task(
    title: str, task_id: str, movie_id: str, dest_dir: str, plugin_names: List[str], release_data: Optional[str]
) -> Dict[str, Any]:
    await task_logic.start_task(task_id)
    await plugin_manager.download_artwork(title, dest_dir, release_data, prefer_order=plugin_names)
    movie_update = {
        "has_poster": True,
        "has_backdrop": False,
        "has_thumbnail": True,
    }
    await movie_logic.update_movies([movie_id], movie_update)
    await task_logic.complete_task(task_id, result={})

@task_handler("下载指定演员的大头照")
async def download_actor_thumb_task(
    actor_name: str, task_id: str, dest_dir: str, plugin_names: List[str]
) -> Dict[str, Any]:
    await task_logic.start_task(task_id)
    await plugin_manager.download_actor_portrait(actor_name, dest_dir, prefer_order=plugin_names)
    await task_logic.complete_task(task_id, result={})

@task_handler("下载指定的字幕文件")
async def download_subtitle_task(
    title: str, task_id: str, dest_dir: str, plugin_names: List[str], release_data: Optional[str]
) -> Dict[str, Any]:
    await task_logic.start_task(task_id)
    await plugin_manager.download_subtitle(title, dest_dir, release_data, prefer_order=plugin_names)
    await task_logic.complete_task(task_id, result={})
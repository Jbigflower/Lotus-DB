from typing import Dict, Any, List
from src.core.handler import task_handler
from src.logic import MovieLogic, TaskLogic
from src.logic.file.film_asset_file_ops import FilmAssetFileOps
from src.plugins.manager import PluginManager

plugin_manager = PluginManager()
task_logic = TaskLogic()
movie_logic = MovieLogic()
film_asset_file_ops = FilmAssetFileOps()


@task_handler("批量导入电影")
async def import_movies_task(
    movies_data: List[Dict[str, Any]], task_id: str, library: dict
) -> Dict[str, Any]:
    try:
        library_id = library["id"]
        library_path = library["path"]
        activated_plugins = library["activated_plugins"].get('metadata', [])
        await task_logic.start_task(task_id)
        # 1）批量插入电影数据
        movies = await movie_logic.create_batch(movies_data, library_id=library_id)
        # 2）批量下载电影封面、海报……
        movie_titles = [movie.title for movie in movies]
        movie_ids = [movie.id for movie in movies]
        movie_release_dates = [movie.release_date for movie in movies]
        dest_dirs = [film_asset_file_ops._get_movie_path(library_id, movie_id) for movie_id in movie_ids]
        results = await plugin_manager.download_artworks(
            titles=movie_titles,
            movie_ids=movie_ids,
            release_dates=movie_release_dates,
            dest_dir=dest_dirs,
            prefer_order=activated_plugins
        )
        update_dict = {}
        for mid, result in zip(movie_ids, results):
            update_dict[mid] = result
        await movie_logic.update_movie_artworks(movie_ids, update_dict)
        # 3）批量下载电影参演人员
        actors = set()
        exist_actor = await film_asset_file_ops.get_exist_actors(library_path)
        for movie in movies:
            actors.update(movie.actors)
            actors.update(movie.directors)
        actors -= exist_actor
        actors = list(actors)
        await plugin_manager.download_actor_portraits(
            actor_names=actors,
            dest_dir=[film_asset_file_ops._get_actor_path(library_id, actor_name) for actor_name in actors],
            prefer_order=activated_plugins
        )
        # 4）完成任务
        await task_logic.complete_task(task_id, result={})
        return {"status": "success", "count": len(movies_data)}
    except Exception as e:
        await task_logic.fail_task(task_id, str(e))
        return {"status": "failed", "error": str(e)}

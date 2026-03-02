# 顶部导入与任务内二次导入修正
import os
import glob
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any

from src.core.handler import task_handler
from src.logic import TaskLogic, LibraryLogic, MovieLogic


def migrate_library_structure(
    root_path: str,
    old_structure: Dict[str, str],
    new_structure: Dict[str, str],
    movie_ids: list[str],
):
    """
    媒体库结构迁移工具

    :param root_path: 媒体库根路径
    :param old_structure: 原 LibraryStructure.dict()
    :param new_structure: 新 LibraryStructure.dict()
    :param movie_ids: 所有电影的 MongoID 列表
    """
    root = Path(root_path)
    for movie_id in movie_ids:
        context = {"movie_id": movie_id}
        for key, old_pattern in old_structure.items():
            new_pattern = new_structure.get(key)
            if not new_pattern:
                continue
            old_path_pattern = str(root / old_pattern.format(**context))
            new_path_pattern = str(root / new_pattern.format(**context))
            old_files = glob.glob(old_path_pattern)
            if not old_files:
                continue
            for old_file in old_files:
                old_file_path = Path(old_file)
                if old_file_path.is_dir():
                    if "*" in new_path_pattern:
                        continue
                    new_dir = Path(new_path_pattern)
                    new_dir.mkdir(parents=True, exist_ok=True)
                    if old_file_path.resolve() != new_dir.resolve():
                        _move_all(str(old_file_path), str(new_dir))
                        try:
                            if not any(old_file_path.iterdir()):
                                old_file_path.rmdir()
                        except Exception:
                            pass
                    continue
                new_dir = (
                    Path(new_path_pattern).parent
                    if "*" in new_path_pattern
                    else Path(new_path_pattern)
                )
                new_dir.mkdir(parents=True, exist_ok=True)
                new_file_path = new_dir / old_file_path.name
                if new_file_path.exists():
                    if new_file_path.is_file():
                        new_file_path.unlink()
                    else:
                        pass
                shutil.move(str(old_file_path), str(new_file_path))


def _move_all(from_path: str, to_path: str) -> None:
    os.makedirs(to_path, exist_ok=True)
    for entry in os.listdir(from_path):
        src = os.path.join(from_path, entry)
        dst = os.path.join(to_path, entry)
        if not os.path.exists(dst):
            shutil.move(src, dst)
        elif os.path.isdir(src):
            for root, dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                tgt_dir = os.path.join(dst, rel) if rel != "." else dst
                os.makedirs(tgt_dir, exist_ok=True)
                for f in files:
                    shutil.move(os.path.join(root, f), os.path.join(tgt_dir, f))
        else:
            shutil.move(src, dst)


def _copy_all(from_path: str, to_path: str) -> None:
    os.makedirs(to_path, exist_ok=True)
    for entry in os.listdir(from_path):
        src = os.path.join(from_path, entry)
        dst = os.path.join(to_path, entry)
        if not os.path.exists(dst):
            shutil.copy(src, dst)
        elif os.path.isdir(src):
            for root, dirs, files in os.walk(src):
                rel = os.path.relpath(root, src)
                tgt_dir = os.path.join(dst, rel) if rel != "." else dst
                os.makedirs(tgt_dir, exist_ok=True)
                for f in files:
                    shutil.copy(os.path.join(root, f), os.path.join(tgt_dir, f))
        else:
            shutil.copy(src, dst)


@task_handler("重构库结构任务")
async def refactor_library_structure_task(
    library_id: str, old_version: Dict, new_version: Dict, task_id: str
) -> Dict:
    """
    重构库结构任务：
    - 从 old_version 到 new_version 迁移库结构
    - 确保库索引的一致性
    """
    from src.models import LibraryUpdate, LibraryStructure
    from src.logic.media.media_logic import ensure_dir_rw, resolve_library_root

    task_logic = TaskLogic()
    lib_logic = LibraryLogic()
    mov_logic = MovieLogic()
    try:
        await task_logic.start_task(task_id)
        old_root = resolve_library_root(old_version.get("root_path"))
        new_root_input = new_version.get("root_path")
        new_root = resolve_library_root(new_root_input) if new_root_input else old_root
        root_changed = old_root != new_root
        if root_changed:
            ensure_dir_rw(new_root)
            _copy_all(old_root, new_root)
        old_structure_dict = old_version.get("structure")
        new_structure_dict = new_version.get("structure")
        if old_structure_dict and new_structure_dict:
            old_structure = LibraryStructure(**old_structure_dict)
            new_structure = LibraryStructure(**new_structure_dict)
            if old_structure != new_structure:
                movie_ids = await mov_logic.list_movie_ids(library_id=library_id)
                migrate_library_structure(
                    new_root,
                    old_structure.model_dump(),
                    new_structure.model_dump(),
                    movie_ids,
                )
        await lib_logic.update_library(library_id, LibraryUpdate(**new_version))
        if root_changed:
            shutil.rmtree(old_root)
        await task_logic.complete_task(task_id, result={"structure_updated": True})
    except Exception as e:
        await task_logic.fail_task(task_id, str(e))
        return {"status": "failed", "error": str(e)}


@task_handler("清理库文件")
async def cleanup_library_files_task(root_path: str, task_id: str) -> Dict[str, Any]:
    task_logic = TaskLogic()
    try:
        await task_logic.start_task(task_id)
        await asyncio.to_thread(
            shutil.rmtree, resolve_library_root(root_path), ignore_errors=True
        )
        await task_logic.complete_task(task_id, result={"deleted_root": root_path})
        return {"status": "success", "deleted_root": root_path}
    except Exception as e:
        await task_logic.fail_task(task_id, str(e))
        raise

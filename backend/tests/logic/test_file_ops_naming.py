import re
from src.logic.file.film_asset_file_ops import FilmAssetFileOps
from src.logic.file.user_asset_file_ops import UserAssetFileOps


def test_film_asset_timestamp_name(tmp_path):
    ops = FilmAssetFileOps()
    name = ops._next_sequential_name(str(tmp_path), "mp4")
    assert re.match(r"^\d{8}_\d{6}\.mp4$", name)


def test_user_asset_timestamp_name(tmp_path):
    ops = UserAssetFileOps()
    name = ops._next_sequential_name(str(tmp_path), "jpg")
    assert re.match(r"^\d{8}_\d{6}\.jpg$", name)
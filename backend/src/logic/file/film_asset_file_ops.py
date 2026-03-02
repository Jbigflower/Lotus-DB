import os
import uuid
import shutil
import errno
import requests
from datetime import datetime, timezone
from fastapi import UploadFile

import base64
import hashlib
import time
from typing import Tuple
from config.setting import get_settings
settings = get_settings()


class FilmAssetFileOps:
    LIBRARY_PREFIX = settings.media.library_prefix
    LIBRARY_NGINX_PREFIX = settings.media.nginx_library_location
    LIBRARY_NGINX_TTL = settings.media.secure_link_ttl_seconds
    LIBRARY_NGINX_P_SIG = settings.media.secure_link_param_signature
    LIBRARY_NGINX_P_EXP = settings.media.secure_link_param_expires
    LIBRARY_NGINX_SECRET = settings.media.secure_link_secret
    LIBRARY_NGINX_BASE_URL = settings.media.nginx_static_base_url

    LIBRARY_COVER = 'backdrop.jpg'
    MOVIE_POSTER = 'poster.jpg'
    MOVIE_BACKDROP = 'backdrop.jpg'
    ACTOR_FOLDER = 'commmond'

    # ---- 路径/目录处理（内置） ----
    def _resolve_library_root(self, root_path: str) -> str:
        prefix = os.path.normpath(self.LIBRARY_PREFIX)
        if not root_path:
            return prefix
        rp = os.path.normpath(root_path)
        if os.path.isabs(rp):
            return rp
        if rp.startswith(prefix):
            return rp
        return os.path.normpath(os.path.join(prefix, rp))

    def _mask_library_root(self, full_root: str) -> str:
        pref = os.path.normpath(self.LIBRARY_PREFIX)
        fr = os.path.normpath(full_root or "")
        try:
            masked = os.path.relpath(fr, pref)
        except ValueError:
            masked = fr
        return "" if masked == "." else masked

    def _normalize_dest_dir(self, dest_path: str) -> str:
        tail = os.path.basename(dest_path)
        if ("*" in tail) or ("." in tail):
            return os.path.dirname(dest_path)
        return dest_path

    def make_dir_rw(self, path: str) -> None:
        abs_path = self._resolve_library_root(path)
        if not os.path.isdir(abs_path):
            os.makedirs(abs_path, exist_ok=True)
        if not (os.access(abs_path, os.R_OK) and os.access(abs_path, os.W_OK)):
            raise PermissionError("路径需可读写")

    def _next_sequential_name(self, dest_dir: str, ext: str) -> str:
        ext = ext.lstrip(".")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{ts}.{ext}"

    def check_dir_exists(self, path: str) -> None:
        abs_path = self._resolve_library_root(path)
        if not os.path.isdir(abs_path):
            raise FileNotFoundError(f"目录不存在: {abs_path}")

    def check_file_exists(self, path: str) -> None:
        abs_path = self._resolve_library_root(path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"文件不存在: {abs_path}")

    # ---- Secure Link（集成） ----
    def _urlsafe_b64_no_padding(self, raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def _sanitize_rel_path(self, p: str) -> str:
        p = p.lstrip("/")
        norm = os.path.normpath(p)
        if norm.startswith("..") or os.path.isabs(norm):
            raise ValueError("非法资源路径")
        return norm.replace("\\", "/")

    def _sign_uri(self, uri: str, expires_ts: int, secret: str) -> str:
        s = f"{expires_ts}{uri} {secret}".encode("utf-8")
        digest = hashlib.md5(s).digest()
        return self._urlsafe_b64_no_padding(digest)

    def build_signed_url_for_uri(self, uri_path: str, expires_in_seconds: int = None) -> Tuple[str, int]:
        ttl = expires_in_seconds or self.LIBRARY_NGINX_TTL
        expires_ts = int(time.time()) + int(ttl)

        sig = self._sign_uri(
            uri=uri_path,
            expires_ts=expires_ts,
            secret=self.LIBRARY_NGINX_SECRET,
        )
        p_sig = self.LIBRARY_NGINX_P_SIG
        p_exp = self.LIBRARY_NGINX_P_EXP

        full_url = f"{self.LIBRARY_NGINX_BASE_URL}{uri_path}?{p_sig}={sig}&{p_exp}={expires_ts}"
        return full_url, expires_ts

    def build_library_signed_url(self, library_id: str, resource_path: str, expires_in_seconds: int = None) -> Tuple[str, int]:
        resource_path = self._sanitize_rel_path(resource_path)
        base = self.LIBRARY_NGINX_PREFIX.rstrip("/")
        uri = f"{base}/{library_id}/{resource_path}"
        return self.build_signed_url_for_uri(uri, expires_in_seconds)
    
    # ---- 便捷的资产签名路径操作 ----
    def get_asset_signed_url(self, library_id, asset_path: str, expires_in_seconds: int = None) -> Tuple[str, int]:
        asset_path = self._sanitize_rel_path(asset_path)
        return self.build_library_signed_url(library_id, asset_path, expires_in_seconds)

    def get_movie_poster_signed_url(self, library_id, movie_id):
        poster_path = os.path.join(movie_id, self.MOVIE_POSTER)
        return self.build_library_signed_url(library_id, poster_path)

    def get_movie_backdrop_signed_url(self, library_id, movie_id):
        backdrop_path = os.path.join(movie_id, self.MOVIE_BACKDROP)
        return self.build_library_signed_url(library_id, backdrop_path)

    def get_actor_poster_signed_url(self, library_id, actor_name):
        actor_file = os.path.join(self.ACTOR_FOLDER, actor_name + '.jpg')
        return self.build_library_signed_url(library_id, actor_file)

    def get_library_backdrop_signed_url(self, library_id):
        return self.build_library_signed_url(library_id, self.LIBRARY_COVER)

    def get_asset_thumbnail_signed_url(self, library_id, asset_path):
        session = os.path.splitext(os.path.basename(asset_path))[0]
        thumbnail_folder = os.path.join(os.path.dirname(asset_path), session)
        thumbnail_name = 'thumb_001.jpg'
        return self.build_library_signed_url(library_id, os.path.join(thumbnail_folder, thumbnail_name))

    def get_exist_actors(self, library_path):
        actor_dir = os.path.join(self._resolve_library_root(library_path), self.ACTOR_FOLDER)
        actor_dirs = os.listdir(actor_dir)
        actor_names = [name.split('.')[0] for name in actor_dirs if name.endswith('.jpg')]
        return set(actor_names)

    # ---- 获取实际地址 ----
    def _get_asset_file_path(self, library_id, asset_path):
        return os.path.join(self._resolve_library_root(library_id), asset_path)

    def _get_movie_path(self, library_id, movie_id):
        return os.path.join(self._resolve_library_root(library_id), movie_id)

    def _get_actor_path(self, library_id, actor_name):
        return os.path.join(self._resolve_library_root(library_id), self.ACTOR_FOLDER, actor_name + '.jpg')

    # ---- 资产保存 ----
    def save_library_cover(self, upload: UploadFile, library_id: str):
        backdrop_path = os.path.join(self._resolve_library_root(library_id), self.LIBRARY_COVER)
        self.make_dir_rw(os.path.dirname(backdrop_path))
        with open(backdrop_path, "wb") as f:
            shutil.copyfileobj(upload.file, f)

    def save_movie_poster(self, upload: UploadFile, library_id: str, movie_id: str) -> str:
        dest_dir = os.path.join(self._resolve_library_root(library_id), movie_id)
        self.make_dir_rw(dest_dir)
        poster_file = os.path.join(dest_dir, self.MOVIE_POSTER)
        with open(poster_file, 'wb') as f:
            shutil.copyfileobj(upload.file, f)
        return self.get_movie_poster_signed_url(library_id, movie_id)

    def save_movie_backdrop(self, upload: UploadFile, library_id: str, movie_id: str) -> str:
        dest_dir = os.path.join(self._resolve_library_root(library_id), movie_id)
        self.make_dir_rw(dest_dir)
        backdrop_file = os.path.join(dest_dir, self.MOVIE_BACKDROP)
        with open(backdrop_file, 'wb') as f:
            shutil.copyfileobj(upload.file, f)
        return self.get_movie_backdrop_signed_url(library_id, movie_id)

    def smart_download_file_to_library(
        self, url: str, dest_path: str, asset_ext: str
    ):
        dest_dir = self._resolve_library_root(dest_path)
        dest_dir = self._normalize_dest_dir(dest_dir)
        self.make_dir_rw(dest_dir)
        next_name = self._next_sequential_name(dest_dir, asset_ext)
        save_path = os.path.join(dest_dir, next_name)
        
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
        masked = self._mask_library_root(save_path)
        return masked, next_name, masked        


    def smart_copy_file_to_library(self, src_path: str, dest_path: str, asset_ext: str):
        dest_dir = self._resolve_library_root(dest_path)
        dest_dir = self._normalize_dest_dir(dest_dir)
        self.make_dir_rw(dest_dir)
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"源文件不存在: {src_path}")

        next_name = self._next_sequential_name(dest_dir, asset_ext)
        save_path = os.path.join(dest_dir, next_name)
        shutil.copy2(src_path, save_path)
        masked = self._mask_library_root(save_path)
        return masked, next_name, masked

    def smart_save_upload_to_library(
        self, upload: UploadFile, dest_path: str, asset_ext: str
    ):
        dest_dir = self._resolve_library_root(dest_path)
        dest_dir = self._normalize_dest_dir(dest_dir)
        self.make_dir_rw(dest_dir)

        next_name = self._next_sequential_name(dest_dir, asset_ext)
        save_path = os.path.join(dest_dir, next_name)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        masked = self._mask_library_root(save_path)
        return masked, next_name, masked

    @staticmethod
    def _handle_rmtree_error(func, path, exc_info):
        """
        Handle errors during shutil.rmtree.
        Ignores FileNotFoundError (file already deleted).
        """
        exc_type, exc_value, _ = exc_info
        if issubclass(exc_type, FileNotFoundError):
            return
        if hasattr(exc_value, 'errno') and exc_value.errno == errno.ENOENT:
            return
        # Re-raise other errors
        raise exc_value

    def delete_file(self, file_path: str):
        file_path = self._resolve_library_root(file_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
        dir_name = os.path.splitext(os.path.basename(file_path))[0]
        dir_path = os.path.dirname(file_path)
        candidate_dir = os.path.join(dir_path, dir_name)
        if os.path.isdir(candidate_dir):
            shutil.rmtree(candidate_dir, onerror=self._handle_rmtree_error)

    def delete_dir(self, dir_path: str):
        dir_path = self._resolve_library_root(dir_path)
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path, onerror=self._handle_rmtree_error)


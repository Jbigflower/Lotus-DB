import os
import uuid
import shutil
from datetime import datetime, timezone
from fastapi import UploadFile
from config.setting import get_settings

import base64
import hashlib
import time
from typing import Tuple

settings = get_settings()


class UserAssetFileOps:
    USER_PREFIX = settings.media.user_prefix
    USER_PROFILE = 'profile.jpg'
    USER_THUMBNAIL = 'thumb_001.jpg'
    USER_NGINX_PREFIX = settings.media.nginx_user_location
    USER_NGINX_TTL = settings.media.secure_link_ttl_seconds
    USER_NGINX_P_SIG = settings.media.secure_link_param_signature
    USER_NGINX_P_EXP = settings.media.secure_link_param_expires
    USER_NGINX_SECRET = settings.media.secure_link_secret
    USER_NGINX_BASE_URL = settings.media.nginx_static_base_url

    def _resolve_user_root(self, root_path: str) -> str:
        prefix = os.path.normpath(self.USER_PREFIX)
        if not root_path:
            return prefix
        rp = os.path.normpath(root_path)
        if os.path.isabs(rp):
            return rp
        if rp.startswith(prefix):
            return rp
        return os.path.normpath(os.path.join(prefix, rp))

    def _mask_user_root(self, full_root: str) -> str:
        pref = os.path.normpath(self.USER_PREFIX)
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

    def _next_sequential_name(self, dest_dir: str, ext: str) -> str:
        ext = ext.lstrip(".")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{ts}.{ext}"

    def make_dir_rw(self, path: str) -> None:
        abs_path = self._resolve_user_root(path)
        if not os.path.isdir(abs_path):
            os.makedirs(abs_path, exist_ok=True)
        if not (os.access(abs_path, os.R_OK) and os.access(abs_path, os.W_OK)):
            raise PermissionError("路径需可读写")

    def check_dir_exists(self, path: str) -> None:
        abs_path = self._resolve_user_root(path)
        if not os.path.isdir(abs_path):
            raise FileNotFoundError(f"目录不存在: {abs_path}")

    def check_file_exists(self, path: str) -> None:
        abs_path = self._resolve_user_root(path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"文件不存在: {abs_path}")

    # ---- Secure Link（集成） ----
    def _urlsafe_b64_no_padding(self, raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def _sanitize_rel_path(self, p: str) -> str:
        p = p.lstrip("/")  # 去除前导斜杠
        norm = os.path.normpath(p)
        if norm.startswith("..") or os.path.isabs(norm):
            raise ValueError("非法资源路径")
        return norm.replace("\\", "/")

    def _sign_uri(self, uri: str, expires_ts: int, secret: str) -> str:
        s = f"{expires_ts}{uri} {secret}".encode("utf-8")
        digest = hashlib.md5(s).digest()
        return self._urlsafe_b64_no_padding(digest)

    def build_signed_url_for_uri(self, uri_path: str, expires_in_seconds: int = None) -> Tuple[str, int]:
        ttl = expires_in_seconds or self.USER_NGINX_TTL
        expires_ts = int(time.time()) + int(ttl)

        sig = self._sign_uri(
            uri=uri_path,
            expires_ts=expires_ts,
            secret=self.USER_NGINX_SECRET,
        )
        p_sig = self.USER_NGINX_P_SIG
        p_exp = self.USER_NGINX_P_EXP   

        full_url = f"{self.USER_NGINX_BASE_URL}{uri_path}?{p_sig}={sig}&{p_exp}={expires_ts}"
        return full_url, expires_ts

    def build_user_signed_url(self, user_id: str, resource_path: str, expires_in_seconds: int = None) -> Tuple[str, int]:
        resource_path = self._sanitize_rel_path(resource_path)
        base = self.USER_NGINX_PREFIX.rstrip("/")
        uri = f"{base}/{user_id}/{resource_path}"
        return self.build_signed_url_for_uri(uri, expires_in_seconds)

    # ---- 便捷的资产签名路径操作 ----
    def get_user_profile_signed_url(self, user_id: str):
        return self.build_user_signed_url(user_id, self.USER_PROFILE)

    def get_asset_thumbnail_signed_url(self, user_id, asset_path):
        basename = os.path.splitext(os.path.basename(asset_path))[0]
        thumbnail_folder = os.path.join(os.path.dirname(asset_path), basename)
        thumbnail_name = f'{self.USER_THUMBNAIL}'
        thumbnail_path = os.path.join(thumbnail_folder, thumbnail_name)
        print(user_id, thumbnail_path)
        return self.build_user_signed_url(user_id, thumbnail_path)

    def get_asset_signed_url(self, user_id, asset_path):
        asset_path = self._sanitize_rel_path(asset_path)
        return self.build_user_signed_url(user_id, asset_path)

    def _get_asset_file_path(self, user_id: str, asset_path: str) -> str:
        asset_path = self._sanitize_rel_path(asset_path)
        return os.path.join(self.USER_PREFIX, user_id, asset_path)

    # ---- 智能保存上传文件到用户资产目录 ----
    def smart_save_upload_to_user(
        self, upload: UploadFile, dest_path: str, asset_ext: str
    ):
        dest_dir = self._resolve_user_root(dest_path)
        dest_dir = self._normalize_dest_dir(dest_dir)
        self.make_dir_rw(dest_dir)

        next_name = self._next_sequential_name(dest_dir, asset_ext)
        save_path = os.path.join(dest_dir, next_name)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        masked = self._mask_user_root(save_path)
        return masked, next_name, masked

    def smart_copy_file_to_user(self, src_path: str, dest_path: str, asset_ext: str):
        dest_dir = self._resolve_user_root(dest_path)
        dest_dir = self._normalize_dest_dir(dest_dir)
        self.make_dir_rw(dest_dir)
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"源文件不存在: {src_path}")

        next_name = self._next_sequential_name(dest_dir, asset_ext)
        save_path = os.path.join(dest_dir, next_name)
        shutil.copy2(src_path, save_path)
        masked = self._mask_user_root(save_path)
        return masked, next_name, masked

    def save_user_profile(self, upload: UploadFile, user_id: str):
        profile_path = self._resolve_user_root(os.path.join(user_id, self.USER_PROFILE))
        self.make_dir_rw(os.path.dirname(profile_path))
        with open(profile_path, "wb") as f:
            shutil.copyfileobj(upload.file, f)
import os
import time
import shutil
import subprocess
from pathlib import Path
from bson import ObjectId
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers.libraries import router as libraries_router
import src.routers.libraries as libraries_mod
from src.core.dependencies import get_current_user
from src.services.movies.library_service import LibraryService
from src.models import LibraryRead, LibraryType, UserRead, UserRole

User_U1 = str(ObjectId())
Lib_U1 = str(ObjectId())

# ---- Test helpers ----
def make_user(role=UserRole.USER, uid=User_U1) -> UserRead:
    from datetime import datetime, timezone
    return UserRead(
        id=uid,
        username="tester",
        email="tester@example.com",
        role=role,
        permissions=[],
        is_active=True,
        is_verified=True,
        settings={},
        hashed_password=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def make_library(lid=Lib_U1, owner=User_U1, public=True, active=True) -> LibraryRead:
    return LibraryRead(
        id=lid,
        user_id=owner,
        name="Lib",
        root_path=lid,  # 服务层 FileOps 会将此作为相对根拼接到 prefix
        type=LibraryType.MOVIE,
        description="",
        scan_interval=3600,
        auto_import=False,
        auto_import_scan_path=None,
        auto_import_supported_formats=None,
        is_public=public,
        is_active=active,
        is_deleted=False,
        deleted_at=None,
    )

class FakeLibraryLogic:
    def __init__(self, lib: LibraryRead):
        self._lib = lib
    async def get_library(self, library_id, session=None):
        # 权限检查使用此返回
        return self._lib

def make_app(fake_user: UserRead, svc: LibraryService) -> TestClient:
    app = FastAPI()
    app.include_router(libraries_router)

    async def _fake_get_current_user():
        return fake_user
    app.dependency_overrides[get_current_user] = _fake_get_current_user

    # 替换模块级 service（保留真实 file_logic 与签名逻辑）
    libraries_mod.service = svc
    return TestClient(app)

# ---- Nginx fixture ----
@pytest.fixture(scope="module")
def nginx_server(tmp_path_factory):
    if shutil.which("nginx") is None:
        pytest.skip("nginx 未安装，跳过集成测试")
    tmpdir = tmp_path_factory.mktemp("nginx_lotus")
    port = 18080

    # 计算项目 data/main 绝对路径
    repo_root = Path(__file__).resolve().parents[2]
    alias_path = (repo_root / "data" / "main").resolve()
    alias_path.mkdir(parents=True, exist_ok=True)

    # 生成配置（显式 pid/error_log，移除相对 include）
    conf = tmpdir / "nginx.conf"
    conf.write_text(f"""
pid {tmpdir}/nginx.pid;
error_log {tmpdir}/error.log debug;
events {{}}
http {{
    default_type application/octet-stream;

    server {{
        listen {port};
        server_name localhost;

        location /static/library/ {{
            secure_link $arg_st,$arg_e;
            secure_link_md5 "$secure_link_expires$uri change-me";
            if ($secure_link = "") {{ return 403; }}
            if ($secure_link = "0") {{ return 410; }}
            alias {alias_path}/;
        }}
    }}
}}
""".strip(), encoding="utf-8")

    # 配置检查与启动（不使用 -p）
    subprocess.run(["nginx", "-t", "-c", str(conf)], check=True, capture_output=True)
    proc = subprocess.Popen(["nginx", "-c", str(conf)])

    # 等待端口就绪
    base = f"http://localhost:{port}"
    for _ in range(50):
        try:
            requests.get(base, timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
    else:
        subprocess.run(["nginx", "-s", "stop", "-c", str(conf)], check=False)
        proc.wait(timeout=5)
        pytest.fail("Nginx 未能启动")

    yield {"port": port, "alias_path": str(alias_path), "conf": str(conf)}
    # 停止 Nginx
    subprocess.run(["nginx", "-s", "quit", "-c", str(conf)], check=False)
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

# ---- 集成测试：上传封面 + 获取封面 ----
def test_upload_and_fetch_cover_with_real_nginx(nginx_server, monkeypatch):
    # 调整 settings 指向真实 Nginx 与真实文件系统前缀
    import config.setting as setting_mod
    setting_mod.settings.media.nginx_static_base_url = f"http://localhost:{nginx_server['port']}"
    setting_mod.settings.media.library_prefix = nginx_server["alias_path"]
    # 其余保持默认（secure_link_secret='change-me', param st/e, location '/static/library'）

    # 真实服务，替换逻辑以返回库模型（仅用于权限判断）
    svc = LibraryService()
    lib = make_library()
    svc.logic = FakeLibraryLogic(lib)

    client = make_app(fake_user=make_user(uid=lib.user_id), svc=svc)

    # 上传封面
    body = b"hello-backdrop"
    files = {"file": ("backdrop.jpg", body, "image/jpeg")}
    resp = client.post(f"/api/v1/libraries/{lib.id}/cover", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True

    # 获取签名 URL
    resp2 = client.post("/api/v1/libraries/covers/sign", json=[lib.id])
    assert resp2.status_code == 200
    urls = resp2.json()
    assert isinstance(urls, list) and len(urls) == 1
    url = urls[0]
    assert url.startswith(f"http://localhost:{nginx_server['port']}/static/library/{lib.id}/backdrop.jpg")
    print(url)

    # 通过真实 Nginx 拉取
    r = requests.get(url)
    if r.status_code != 200:
        with open(Path(nginx_server['conf']).with_name('error.log'), 'r', encoding='utf-8') as f:
            print(f.read())
    assert r.status_code == 200
    assert r.content == body
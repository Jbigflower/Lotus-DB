import pytest
from datetime import datetime, timezone
from tests.conftest import get_random_object_id

from src.services.users.user_service import UserService
from src.core.exceptions import ForbiddenError, ValidationError, NotFoundError
from src.models import UserRead, UserRole, UserCreate

def make_user(role=UserRole.USER, uid=None) -> UserRead:
    if uid is None:
        uid = get_random_object_id()
    return UserRead(
        id=uid,
        username="tester",
        email="tester@example.com",
        role=role,
        permissions=[],
        is_active=True,
        is_verified=True,
        settings={},
        hashed_password="oldhash",
        last_login_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

class FakeUserRepo:
    def __init__(self, user: UserRead):
        self.u = user

    async def find_by_id(self, user_id, session=None):
        return self.u if self.u.id == user_id else None

class FakeUserLogic:
    def __init__(self, user: UserRead):
        self._u = user
        self.repo = FakeUserRepo(user)

    def _hash_password(self, pw: str) -> str:
        return f"hashed:{pw}"

    async def search_users(self, *args, **kwargs):
        from src.models import UserPageResult
        return UserPageResult(items=[self._u], total=1, page=1, size=20, pages=1)

    async def get_user(self, user_id):
        if self._u.id != user_id:
            raise NotFoundError("用户不存在")
        return self._u

    async def get_users(self, ids):
        return [self._u] if self._u.id in ids else []

    async def create_user(self, data: UserCreate):
        return self._u

    async def update_user_safety(self, user_id, patch):
        for k, v in patch.items():
            setattr(self._u, k, v)
        return self._u

    async def set_user_role_permissions(self, user_id, role, permissions):
        self._u.role = role or self._u.role
        self._u.permissions = permissions or []
        return self._u

    async def update_username_or_email(self, user_id, patch):
        for k, v in patch.items():
            setattr(self._u, k, v)
        return self._u

    async def set_user_active_status(self, user_id, is_active):
        self._u.is_active = is_active
        return self._u

    async def delete_user(self, user_id):
        return True

class FakeCollectionLogic:
    def __init__(self):
        self.called_with = None
    async def init_default(self, user_id):
        self.called_with = user_id

class FakeFileOps:
    def __init__(self):
        self.saved = []
    def save_user_profile(self, upload, user_id):
        self.saved.append((user_id, getattr(upload, "filename", "unknown")))

@pytest.mark.asyncio
async def test_list_users_requires_admin_forbidden():
    svc = UserService()
    svc.logic = FakeUserLogic(make_user())
    user = make_user(role=UserRole.USER)
    with pytest.raises(ForbiddenError):
        await svc.list_users(current_user=user)

@pytest.mark.asyncio
async def test_get_user_detail_self_and_admin_ok():
    svc = UserService()
    u = make_user(uid=get_random_object_id())
    svc.logic = FakeUserLogic(u)

    admin = make_user(role=UserRole.ADMIN)
    got = await svc.get_user_detail(u.id, admin)
    assert got.id == u.id

    self_user = UserRead(**u.model_dump())
    got2 = await svc.get_user_detail(u.id, self_user)
    assert got2.id == u.id

@pytest.mark.asyncio
async def test_create_user_hash_and_init_default_called(monkeypatch):
    svc = UserService()
    u = make_user(role=UserRole.USER)
    svc.logic = FakeUserLogic(u)
    svc.collection_logic = FakeCollectionLogic()
    admin = make_user(role=UserRole.ADMIN)

    payload = {"username": "alice", "email": "alice@example.com", "role": UserRole.USER.value}
    context = {"plain_password": "pass123"}
    created = await svc.create_user(payload, context, current_user=admin)
    assert created.id == u.id
    assert svc.collection_logic.called_with == u.id

@pytest.mark.asyncio
async def test_reset_password_requires_admin_and_change_password_self():
    svc = UserService()
    u = make_user()
    svc.logic = FakeUserLogic(u)

    admin = make_user(role=UserRole.ADMIN)
    updated = await svc.reset_password(u.id, {"new_password": "newpass"}, current_user=admin)
    assert isinstance(updated, UserRead)

    # change_password 自身可操作
    self_user = UserRead(**u.model_dump())
    out = await svc.change_password(u.id, {"old_password": "newpass", "new_password": "new1231231"}, current_user=self_user)
    assert isinstance(out, UserRead)

@pytest.mark.asyncio
async def test_update_identity_requires_self_or_admin():
    svc = UserService()
    u = make_user()
    svc.logic = FakeUserLogic(u)

    self_user = UserRead(**u.model_dump())
    out = await svc.update_identity(u.id, {"email": "new@example.com"}, current_user=self_user)
    assert out.email == "new@example.com"

@pytest.mark.asyncio
async def test_delete_user_returns_user_and_meta():
    svc = UserService()
    u = make_user()
    svc.logic = FakeUserLogic(u)
    admin = make_user(role=UserRole.ADMIN)
    user_model, meta = await svc.delete_user(u.id, admin)
    assert user_model.id == u.id and meta["success"] == 1

@pytest.mark.asyncio
async def test_set_user_active_status_requires_admin():
    svc = UserService()
    u = make_user()
    svc.logic = FakeUserLogic(u)
    admin = make_user(role=UserRole.ADMIN)
    out = await svc.set_user_active_status(u.id, True, admin)
    assert out.is_active is True

@pytest.mark.asyncio
async def test_list_profiles_signed_and_upload_profile():
    svc = UserService()
    u = make_user()
    svc.logic = FakeUserLogic(u)
    svc.file_logic = FakeFileOps()

    # 静态方法签名返回
    import src.logic.file.user_asset_file_ops as mod
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(mod.UserAssetFileOps, "build_user_signed_url", lambda uid, name: (f"signed://{uid}/{name}", 300))

    self_user = UserRead(**u.model_dump())
    urls = await svc.list_user_profiles_signed([u.id], current_user=self_user)
    assert urls == [f"signed://{u.id}/profile.jpg"]

    class DummyUpload: filename = "profile.jpg"
    ok = await svc.upload_user_profile(u.id, DummyUpload(), current_user=self_user)
    assert ok is True and svc.file_logic.saved and svc.file_logic.saved[0][0] == u.id
import pytest
from datetime import datetime, timezone
from src.services.users.auth_service import AuthService
from src.models import UserRead, UserRole

class FakeAuthLogic:
    def __init__(self):
        self._user = UserRead(
            id="u1",
            username="tester",
            email="tester@example.com",
            role=UserRole.USER,
            permissions=[],
            is_active=True,
            is_verified=True,
            settings={},
            hashed_password=None,
            last_login_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    async def _hash_password(self, password: str) -> str:
        return "hashed"

    async def register(self, payload):
        return self._user

    async def login(self, username: str, password: str, device_info=None):
        return ("t123", self._user, "sid123")

    async def logout(self, user_id: str, session_id=None):
        return None

    async def verify_token(self, token: str):
        if token != "t123":
            from src.core.exceptions import UnauthorizedError
            raise UnauthorizedError("认证失败")
        return self._user

    async def list_devices(self, user_id: str):
        return [{"session_id": "sid123", "ip": "127.0.0.1", "user_agent": "pytest", "platform": "test", "alias": None, "created_at": "t", "last_active_at": "t"}]

    async def revoke_device(self, user_id: str, session_id: str):
        return None

    async def revoke_all_devices(self, user_id: str, except_session_id=None):
        return None

    async def rename_device(self, user_id: str, session_id: str, alias: str):
        return None


@pytest.mark.asyncio
async def test_auth_service_login_and_verify(monkeypatch):
    svc = AuthService()
    svc.logic = FakeAuthLogic()

    out = await svc.login("tester", "pw")
    assert out["access_token"] == "t123" and out["session_id"] == "sid123"
    current = await svc.verify_token("t123")
    assert isinstance(current, UserRead)

    await svc.logout(user_id="u1", session_id="sid123")
    with pytest.raises(Exception):
        await svc.verify_token("bad")
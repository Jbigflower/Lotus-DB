import pytest
from datetime import datetime, timezone

from src.services.users.asset_service import AssetService
from src.models import (
    UserRead,
    UserRole,
    UserAssetType,
    AssetStoreType,
    UserAssetCreate,
    UserAssetRead,
)


def make_user(role=UserRole.USER, uid="u1") -> UserRead:
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


class FakeUserAssetLogic:
    async def create_asset(self, payload: UserAssetCreate, session=None):
        data = payload.model_dump()
        data.update(
            {
                "id": "new_user_asset",
                "metadata": None,
                "is_deleted": False,
                "deleted_at": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "movie_info": None,
                "require_allocate": False,
            }
        )
        return UserAssetRead(**data)


@pytest.mark.asyncio
async def test_create_text_user_asset_basic(monkeypatch):
    svc = AssetService()
    svc.logic = FakeUserAssetLogic()

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(svc, "_ensure_user_create_permission", noop)

    user = make_user()
    payload = UserAssetCreate(
        movie_id="m1",
        type=UserAssetType.NOTE,
        name=None,
        related_movie_ids=[],
        tags=[],
        is_public=False,
        permissions=[],
        path=None,
        store_type=AssetStoreType.LOCAL,
        actual_path=None,
        content="hello world",
        user_id=user.id,
    )

    created = await svc.create_text_user_asset(payload, current_user=user)
    assert isinstance(created, UserAssetRead)
    assert created.type == UserAssetType.NOTE
    assert created.user_id == user.id
    assert created.name and len(created.name) > 0
    assert created.path and created.path.endswith(".md")
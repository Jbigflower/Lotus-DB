import pytest
from datetime import datetime, timezone
from bson import ObjectId

from src.repos.mongo_repos.users.user_repo import UserRepo
from src.models import UserCreate, UserInDB, UserRole

@pytest.fixture
def repo():
    return UserRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_user_no_soft_delete(repo: UserRepo):
    create = UserCreate(
        username="alice",
        email="alice@example.com",
        role=UserRole.USER,
        hashed_password="hashed_pw",
    )

    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # 基础字段
    assert doc["username"] == "alice"
    assert doc["email"] == "alice@example.com"
    assert doc["hashed_password"] == "hashed_pw"
    # 父类填充的时间戳
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)
    # 未开启软删除，不应该有 is_deleted/deleted_at
    assert "is_deleted" not in doc
    assert "deleted_at" not in doc

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_user_id_mapping(repo: UserRepo):
    docs = [
        {
            "_id": ObjectId(),
            "username": "bob",
            "email": "bob@example.com",
            "role": UserRole.ADMIN,
            "hashed_password": "hashed_pw2",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]
    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: UserInDB = models[0]
    assert isinstance(m.id, str)
    assert m.username == "bob"
    assert m.email == "bob@example.com"
    assert m.hashed_password == "hashed_pw2"
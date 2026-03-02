import pytest
from datetime import datetime, timezone
from bson import ObjectId

from src.repos.mongo_repos.users.user_custom_list_repo import UserCustomListRepo
from src.models import CustomListCreate, CustomListInDB, CustomListType

@pytest.fixture
def repo():
    return UserCustomListRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_user_and_movies_to_objectid(repo: UserCustomListRepo):
    create = CustomListCreate(
        user_id="507f1f77bcf86cd799439011",
        name="MyFav",
        type=CustomListType.FAVORITE,
        description="desc",
        movies=["507f1f77bcf86cd799439012", "507f1f77bcf86cd799439013"],
        is_public=True,
    )
    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]
    # user_id 与 movies 转 ObjectId
    assert isinstance(doc["user_id"], ObjectId)
    assert all(isinstance(x, ObjectId) for x in doc["movies"])
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_user_and_movies_to_str(repo: UserCustomListRepo):
    oid_user = ObjectId("507f1f77bcf86cd799439011")
    oid_mov1 = ObjectId()
    oid_mov2 = ObjectId()
    docs = [
        {
            "_id": ObjectId(),
            "user_id": oid_user,
            "name": "ListB",
            "type": CustomListType.WATCHLIST,
            "description": "",
            "movies": [oid_mov1, oid_mov2],
            "is_public": False,
            "is_deleted": False,
            "deleted_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]
    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: CustomListInDB = models[0]
    assert isinstance(m.id, str)
    assert m.user_id == str(oid_user)
    assert m.movies == [str(oid_mov1), str(oid_mov2)]
    assert m.name == "ListB"
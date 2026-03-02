import pytest
from bson import ObjectId
from datetime import datetime, timezone

from src.repos.mongo_repos.task.task_repo import TaskRepo
from src.models import (
    TaskCreate,
    TaskInDB,
    TaskType,
    TaskSubType,
    TaskPriority,
    TaskStatus,
    ProgressInfo,
)

@pytest.fixture
def repo():
    return TaskRepo()

@pytest.mark.asyncio
async def test_convert_createModel_to_dict_user_id_objectid_and_soft_delete_fields(repo: TaskRepo):
    create = TaskCreate(
        name="Generate Thumbs",
        description="make sprites",
        task_type=TaskType.ANALYSIS,
        sub_type=TaskSubType.THUMB_SPRITE_GENERATE,
        priority=TaskPriority.HIGH,
        parameters={"movie_id": "m123"},
        status=TaskStatus.PENDING,
        progress=ProgressInfo(current_step="", total_steps=10, completed_steps=0),
        result={},
        user_id="507f1f77bcf86cd799439011",
    )

    docs = repo.convert_createModel_to_dict([create])
    assert isinstance(docs, list) and len(docs) == 1
    doc = docs[0]

    # user_id 转 ObjectId
    assert isinstance(doc["user_id"], ObjectId)

    # 父类填充：时间戳与软删除标记
    assert isinstance(doc["created_at"], datetime)
    assert isinstance(doc["updated_at"], datetime)
    assert doc["is_deleted"] is False
    assert doc["deleted_at"] is None

@pytest.mark.asyncio
async def test_convert_dict_to_pydanticModel_user_id_to_str_and_id_mapping(repo: TaskRepo):
    oid_user = ObjectId("507f1f77bcf86cd799439011")
    docs = [
        {
            "_id": ObjectId(),
            "name": "Extract Metadata",
            "description": "extract",
            "task_type": TaskType.ANALYSIS,
            "sub_type": TaskSubType.EXTRACT_METADATA,
            "priority": TaskPriority.NORMAL,
            "parameters": {},
            "status": TaskStatus.RUNNING,
            "progress": ProgressInfo(current_step="start", total_steps=3, completed_steps=1),
            "result": {},
            "user_id": oid_user,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    ]

    models = repo.convert_dict_to_pydanticModel(docs)
    assert isinstance(models, list) and len(models) == 1
    m: TaskInDB = models[0]
    # _id 转 id，user_id 转字符串
    assert isinstance(m.id, str)
    assert m.user_id == str(oid_user)
    assert m.name == "Extract Metadata"
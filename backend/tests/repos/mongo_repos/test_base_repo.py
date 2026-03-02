import pytest
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from bson import ObjectId

from src.repos.mongo_repos.base_repo import BaseRepo
from src.core.exceptions import RepoValidationError, BaseRepoException


# --------------------------- Dummy 模型与仓储 ---------------------------

class DummyInDB(BaseModel):
    id: str
    name: str
    value: int
    created_at: datetime
    updated_at: datetime
    is_deleted: Optional[bool] = None
    deleted_at: Optional[datetime] = None


class DummyCreate(BaseModel):
    name: str
    value: int


class DummyUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[int] = None


class DummyRepo(BaseRepo[DummyInDB, DummyCreate, DummyUpdate]):
    # 设定较小的上限，方便测试 limit 校验
    MAX_FIND_LIMIT = 3

    def __init__(self, soft_delete: bool = True):
        super().__init__(
            collection_name="dummy",
            InDB_Model=DummyInDB,
            Create_Model=DummyCreate,
            Update_Model=DummyUpdate,
            soft_delete=soft_delete,
        )

    # 实现抽象方法，委托给父类默认逻辑
    def convert_createModel_to_dict(self, models: List[DummyCreate]) -> List[Dict[str, Any]]:
        return super().convert_createModel_to_dict(models)

    def convert_dict_to_pydanticModel(self, docs: List[Dict[str, Any]]) -> List[DummyInDB]:
        return super().convert_dict_to_pydanticModel(docs)

# --------------------------- 伪造 Mongo 集合与游标 ---------------------------

class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        # 深拷贝，避免就地修改影响断言
        self._docs = [d.copy() for d in docs]
        self._skip = 0
        self._limit = None
        self._sort = None

    def skip(self, n: int):
        self._skip = n
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def sort(self, sort_params: List[tuple]):
        self._sort = sort_params
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        start = self._skip or 0
        # 以 length 优先，其次是设置的 limit
        end = None
        if length is not None and length >= 0:
            end = start + length
        elif self._limit is not None:
            end = start + self._limit
        result = self._docs[start:end] if end is not None else self._docs[start:]
        return result


class FakeAggCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = [d.copy() for d in docs]

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        return self._docs


class FakeCollection:
    def __init__(self, docs: List[Dict[str, Any]]):
        # 模拟数据库集合存储
        self.docs = [d.copy() for d in docs]

    def _match(self, doc: Dict[str, Any], filter_query: Optional[Dict[str, Any]]) -> bool:
        if not filter_query:
            return True
        for k, v in filter_query.items():
            if doc.get(k) != v:
                return False
        return True

    def find(self, filter_query: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, int]] = None, session=None):
        # 简化：忽略 projection 的具体应用，由 BaseRepo 决定返回类型
        matched = [d for d in self.docs if self._match(d, filter_query)]
        return FakeCursor(matched)

    def aggregate(self, pipeline: List[Dict[str, Any]], session=None):
        # 简化：忽略 pipeline，直接返回当前集合内容
        return FakeAggCursor(self.docs)

    async def find_one_and_update(self, filter_query: Dict[str, Any], update_doc: Dict[str, Any], session=None, return_document: bool = True):
        # update_doc 形如 {"$set": {...}}
        set_doc = update_doc.get("$set", {})
        for i, d in enumerate(self.docs):
            if self._match(d, filter_query):
                self.docs[i].update(set_doc)
                return self.docs[i]
        return None

    async def find_one_and_delete(self, filter_query: Dict[str, Any], session=None):
        for i, d in enumerate(self.docs):
            if self._match(d, filter_query):
                return self.docs.pop(i)
        return None

    async def count_documents(self, filter_query: Dict[str, Any], session=None) -> int:
        return sum(1 for d in self.docs if self._match(d, filter_query))


# --------------------------- 测试用初始数据 ---------------------------

def initial_docs():
    now = datetime.now(timezone.utc)
    return [
        {
            "_id": ObjectId(),
            "name": "doc1",
            "value": 1,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "deleted_at": None,
        },
        {
            "_id": ObjectId(),
            "name": "doc2",
            "value": 2,
            "created_at": now,
            "updated_at": now,
            "is_deleted": True,
            "deleted_at": now,
        },
        {
            "_id": ObjectId(),
            "name": "doc3",
            "value": 3,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "deleted_at": None,
        },
    ]


# --------------------------- BaseRepo 行为覆盖测试 ---------------------------

def test_convert_createModel_to_dict_sets_timestamps_and_soft_delete():
    repo = DummyRepo(soft_delete=True)
    models = [DummyCreate(name="n1", value=10), DummyCreate(name="n2", value=20)]

    docs = repo.convert_createModel_to_dict(models)
    assert len(docs) == 2
    for d in docs:
        assert isinstance(d["created_at"], datetime) and d["created_at"].tzinfo == timezone.utc
        assert isinstance(d["updated_at"], datetime) and d["updated_at"].tzinfo == timezone.utc
        assert d["is_deleted"] is False
        assert d["deleted_at"] is None


def test_convert_dict_to_pydanticModel_maps_id_and_fields():
    repo = DummyRepo()
    now = datetime.now(timezone.utc)
    raw = [
        {
            "_id": ObjectId(),
            "name": "x",
            "value": 7,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "deleted_at": None,
        }
    ]
    models = repo.convert_dict_to_pydanticModel(raw)
    assert len(models) == 1
    m = models[0]
    assert isinstance(m.id, str) and len(m.id) > 0
    assert m.name == "x"
    assert m.value == 7


@pytest.mark.asyncio
async def test_find_projection_invalid_field_raises():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())

    with pytest.raises(RepoValidationError):
        await repo.find(filter_query={}, projection={"unknown": 1})


@pytest.mark.asyncio
async def test_find_with_projection_returns_raw_dicts():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())

    docs = await repo.find(
        filter_query={"is_deleted": False},
        projection={"name": 1},
        limit=repo.MAX_FIND_LIMIT,  # 保证不超过上限
    )
    assert isinstance(docs, list) and len(docs) >= 1
    assert isinstance(docs[0], dict)  # 有 projection 时返回 dict


@pytest.mark.asyncio
async def test_find_without_projection_returns_pydantic_models():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())

    models = await repo.find(
        filter_query={"is_deleted": False},
        limit=repo.MAX_FIND_LIMIT,  # 保证不超过上限
    )
    assert isinstance(models, list) and len(models) >= 1
    assert isinstance(models[0], DummyInDB)


@pytest.mark.asyncio
async def test_find_limit_guard_raises_on_exceed_max():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())

    with pytest.raises(RepoValidationError):
        await repo.find(limit=repo.MAX_FIND_LIMIT + 1)


@pytest.mark.asyncio
async def test_find_skip_and_limit_slice_results():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())
    # 预期：跳过 1，取 1 条
    rows = await repo.find(filter_query={}, skip=1, limit=1, projection={"name": 1})
    assert len(rows) == 1
    assert isinstance(rows[0], dict)


@pytest.mark.asyncio
async def test_update_one_updates_fields_and_returns_model():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())
    updated = await repo.update_one({"name": "doc1"}, {"value": 100})
    assert updated is not None
    assert updated.value == 100


@pytest.mark.asyncio
async def test_delete_one_soft_delete_updates_flags_and_returns_model():
    repo = DummyRepo(soft_delete=True)
    docs = initial_docs()
    # 确保存在一个未软删的文档
    docs[0]["is_deleted"] = False
    repo._collection = FakeCollection(docs)

    result = await repo.delete_one({"name": "doc1"}, soft_delete=True)
    assert result is not None
    assert result.is_deleted is True
    assert isinstance(result.deleted_at, datetime)
    assert isinstance(result.updated_at, datetime)


@pytest.mark.asyncio
async def test_delete_one_hard_delete_when_param_false():
    repo = DummyRepo(soft_delete=True)
    repo._collection = FakeCollection(initial_docs())

    result = await repo.delete_one({"name": "doc3"}, soft_delete=False)
    assert result is not None
    assert result.name == "doc3"
    # 已被物理删除
    count = await repo.collection.count_documents({"name": "doc3"})
    assert count == 0


@pytest.mark.asyncio
async def test_delete_one_soft_delete_requested_but_repo_disabled_raises():
    repo = DummyRepo(soft_delete=False)
    repo._collection = FakeCollection(initial_docs())
    with pytest.raises(BaseRepoException):
        await repo.delete_one({"name": "doc1"}, soft_delete=True)


@pytest.mark.asyncio
async def test_restore_one_recovers_soft_deleted_document():
    repo = DummyRepo(soft_delete=True)
    repo._collection = FakeCollection(initial_docs())

    # 只能恢复 is_deleted=True 的文档
    result = await repo.restore_one({"name": "doc2"})
    assert result is not None
    assert result.is_deleted is False
    assert result.deleted_at is None
    assert isinstance(result.updated_at, datetime)


@pytest.mark.asyncio
async def test_restore_one_raises_when_soft_delete_disabled():
    repo = DummyRepo(soft_delete=False)
    repo._collection = FakeCollection(initial_docs())
    with pytest.raises(BaseRepoException):
        await repo.restore_one({"name": "doc2"})


@pytest.mark.asyncio
async def test_exists_true_and_false():
    repo = DummyRepo()
    repo._collection = FakeCollection(initial_docs())

    assert await repo.exists({"name": "doc1"}) is True
    assert await repo.exists({"name": "not-exist"}) is False


@pytest.mark.asyncio
async def test_aggregate_returns_models_on_valid_docs():
    repo = DummyRepo()
    # 构造满足转换要求的文档
    now = datetime.now(timezone.utc)
    repo._collection = FakeCollection([
        {
            "_id": ObjectId(),
            "name": "agg1",
            "value": 10,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "deleted_at": None,
        },
        {
            "_id": ObjectId(),
            "name": "agg2",
            "value": 20,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "deleted_at": None,
        },
    ])

    out = await repo.aggregate(pipeline=[{"$match": {"is_deleted": False}}])
    assert isinstance(out, list) and len(out) == 2
    assert isinstance(out[0], DummyInDB)
    assert out[0].name == "agg1"


@pytest.mark.asyncio
async def test_aggregate_fallback_to_raw_when_conversion_fails():
    repo = DummyRepo()
    # 构造会触发转换失败的文档（缺少必填字段）
    repo._collection = FakeCollection([
        {"_id": ObjectId(), "name": "bad1"},  # 缺少 value/时间戳
        {"_id": ObjectId(), "value": 99},     # 缺少 name/时间戳
    ])
    out = await repo.aggregate(pipeline=[{"$match": {}}])
    assert isinstance(out, list) and len(out) == 2
    assert isinstance(out[0], dict)
    assert "name" in out[0] or "value" in out[0]


def test_get_range_filter_produces_expected_structure():
    repo = DummyRepo()
    rf = repo._get_range_filter("value", min_value=1, max_value=5)
    assert rf == {"value": {"$gte": 1, "$lte": 5}}

    rf_min_only = repo._get_range_filter("value", min_value=2)
    assert rf_min_only == {"value": {"$gte": 2}}

    rf_max_only = repo._get_range_filter("value", max_value=10)
    assert rf_max_only == {"value": {"$lte": 10}}

    rf_empty = repo._get_range_filter("value")
    assert rf_empty == {}
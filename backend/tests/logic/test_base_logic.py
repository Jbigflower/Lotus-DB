import pytest
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from src.logic.base_logic import BaseLogic
from src.core.exceptions import NotFoundError


# --------- Dummy/Pydantic 模型 ---------

class DummyInDB(BaseModel):
    id: str
    name: str
    is_deleted: bool = False


class DummyCreate(BaseModel):
    name: str


class DummyUpdate(BaseModel):
    name: Optional[str] = None


class DummyRead(BaseModel):
    id: str
    name: str


# --------- Fake Repo（最小接口模拟） ---------

class FakeRepo:
    def __init__(self) -> None:
        self._store: Dict[str, DummyInDB] = {}
        self.find_by_id_calls = 0

    async def find_by_id(self, doc_id: str, session=None) -> Optional[DummyInDB]:
        self.find_by_id_calls += 1
        return self._store.get(doc_id)

    async def find_by_ids(self, doc_ids: List[str], session=None) -> List[DummyInDB]:
        return [self._store[_id] for _id in doc_ids if _id in self._store]

    async def insert_one(self, obj: DummyCreate, session=None) -> DummyInDB:
        new_id = f"new{len(self._store)+1}"
        in_db = DummyInDB(id=new_id, name=obj.name, is_deleted=False)
        self._store[new_id] = in_db
        return in_db

    async def update_by_ids(self, ids: List[str], patch: Dict[str, Any], session=None) -> List[DummyInDB]:
        updated: List[DummyInDB] = []
        for _id in ids:
            if _id in self._store:
                curr = self._store[_id]
                name = patch.get("name", curr.name)
                curr = DummyInDB(id=curr.id, name=name, is_deleted=curr.is_deleted)
                self._store[_id] = curr
                updated.append(curr)
        return updated

    async def update_by_id(self, doc_id: str, patch: Dict[str, Any], session=None) -> Optional[DummyInDB]:
        if doc_id not in self._store:
            return None
        curr = self._store[doc_id]
        name = patch.get("name", curr.name)
        curr = DummyInDB(id=curr.id, name=name, is_deleted=curr.is_deleted)
        self._store[doc_id] = curr
        return curr

    async def delete_by_ids(self, ids: List[str], soft_delete: bool = True, session=None) -> int:
        count = 0
        for _id in ids:
            if _id in self._store:
                if soft_delete:
                    curr = self._store[_id]
                    self._store[_id] = DummyInDB(id=curr.id, name=curr.name, is_deleted=True)
                else:
                    self._store.pop(_id, None)
                count += 1
        return count

    async def delete_by_id(self, doc_id: str, soft_delete: bool = True, session=None) -> int:
        if doc_id not in self._store:
            return 0
        if soft_delete:
            curr = self._store[doc_id]
            self._store[doc_id] = DummyInDB(id=curr.id, name=curr.name, is_deleted=True)
        else:
            self._store.pop(doc_id, None)
        return 1

    async def restore_by_ids(self, ids: List[str], session=None) -> List[DummyInDB]:
        restored: List[DummyInDB] = []
        for _id in ids:
            if _id in self._store:
                curr = self._store[_id]
                curr = DummyInDB(id=curr.id, name=curr.name, is_deleted=False)
                self._store[_id] = curr
                restored.append(curr)
        return restored

    async def restore_by_id(self, doc_id: str, session=None) -> Optional[DummyInDB]:
        if doc_id not in self._store:
            return None
        curr = self._store[doc_id]
        curr = DummyInDB(id=curr.id, name=curr.name, is_deleted=False)
        self._store[doc_id] = curr
        return curr


# --------- Fake Cache（DualLayerCache 接口最小模拟） ---------

class FakeCache:
    def __init__(self) -> None:
        self._detail: Dict[str, Dict[str, Any]] = {}

    async def get_detail(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self._detail.get(item_id)

    async def cache_detail(self, item: Dict[str, Any], expire: Optional[int] = None) -> bool:
        _id = item.get("id")
        if _id is None:
            return False
        self._detail[_id] = item
        return True

    async def get_details_batch(self, item_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        return [self._detail.get(_id) for _id in item_ids]

    async def cache_details_batch(self, items: List[Dict[str, Any]], expire: Optional[int] = None) -> bool:
        for it in items:
            _id = it.get("id")
            if _id is not None:
                self._detail[_id] = it
        return True

    async def clear_item_cache(self, item_id: str) -> bool:
        self._detail.pop(item_id, None)
        return True

    async def delete_search_cache_all(self) -> bool:
        return True

    async def clear_item_cache(self, item_id: str) -> bool:
        # BaseLogic.delete_by_id 会调用
        self._detail.pop(item_id, None)
        return True

    async def get_details_batch(self, item_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        # BaseLogic.get_by_ids 可能会调用
        return [self._detail.get(i) for i in item_ids]

    async def delete_details_batch(self, item_ids: List[str]) -> bool:
        # BaseLogic.deleted_by_ids 会调用
        for i in item_ids:
            self._detail.pop(i, None)
        return True

# --------- 测试用辅助函数 ---------

def make_in_db(_id: str, name: str = "N") -> DummyInDB:
    return DummyInDB(id=_id, name=name, is_deleted=False)


# --------- 单元测试 ---------

@pytest.mark.asyncio
async def test_get_by_id_cache_hit():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    oid = "a1"
    # 预置缓存命中
    await logic.cache_repo.cache_detail(make_in_db(oid, "A").model_dump())

    got = await logic.get_by_id(oid)
    assert isinstance(got, DummyRead)
    assert got.id == oid
    assert logic.repo.find_by_id_calls == 0


@pytest.mark.asyncio
async def test_get_by_id_cache_invalid_then_db_refill():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    oid = "a2"
    # 缓存无效对象（触发 Pydantic 验证失败）
    logic.cache_repo._detail[oid] = {}
    # DB 有值
    logic.repo._store[oid] = make_in_db(oid, "A2")

    got = await logic.get_by_id(oid)
    assert isinstance(got, DummyRead) and got.id == oid
    # 回填缓存成功
    assert logic.cache_repo._detail[oid]["id"] == oid
    assert logic.repo.find_by_id_calls == 1


@pytest.mark.asyncio
async def test_get_by_id_not_found_raises():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    with pytest.raises(NotFoundError):
        await logic.get_by_id("missing")


@pytest.mark.asyncio
async def test_get_by_ids_mixed_cache_and_db_with_ordering():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    ids = ["m1", "m2", "m3"]
    # 缓存命中 m1, m3；m2 走 DB
    await logic.cache_repo.cache_detail(make_in_db("m1", "X").model_dump())
    await logic.cache_repo.cache_detail(make_in_db("m3", "Z").model_dump())
    logic.repo._store["m2"] = make_in_db("m2", "Y")

    res = await logic.get_by_ids(ids, require_sort=True)
    assert isinstance(res, list) and len(res) == 3
    assert [x.id for x in res] == ids
    # 缺失部分已回填缓存
    assert logic.cache_repo._detail["m2"]["id"] == "m2"


@pytest.mark.asyncio
async def test_create_caches_and_returns_read_model():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    created = await logic.create(DummyCreate(name="C1"))
    assert isinstance(created, DummyRead)
    # 缓存已写入
    assert logic.cache_repo._detail[created.id]["id"] == created.id
    # Repo 也有数据
    assert created.id in logic.repo._store


@pytest.mark.asyncio
async def test_update_by_ids_updates_and_caches():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    logic.repo._store["u1"] = make_in_db("u1", "old")
    logic.repo._store["u2"] = make_in_db("u2", "old")

    res = await logic.update_by_ids(["u1", "u2"], {"name": "updated"})
    assert len(res) == 2
    assert {x.name for x in res} == {"updated"}
    # 缓存已回填
    assert logic.cache_repo._detail["u1"]["name"] == "updated"
    assert logic.cache_repo._detail["u2"]["name"] == "updated"


@pytest.mark.asyncio
async def test_update_by_id_not_found_raises():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    with pytest.raises(NotFoundError):
        await logic.update_by_id("nope", {"name": "x"})


@pytest.mark.asyncio
async def test_update_by_id_success_and_cache():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    logic.repo._store["ux"] = make_in_db("ux", "old")
    res = await logic.update_by_id("ux", {"name": "new"})
    assert isinstance(res, DummyRead) and res.name == "new"
    assert logic.cache_repo._detail["ux"]["name"] == "new"


@pytest.mark.asyncio
async def test_deleted_by_ids_soft_delete_and_clear_cache():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    logic.repo._store["d1"] = make_in_db("d1", "D1")
    logic.repo._store["d2"] = make_in_db("d2", "D2")
    await logic.cache_repo.cache_detail(logic.repo._store["d1"].model_dump())
    await logic.cache_repo.cache_detail(logic.repo._store["d2"].model_dump())

    count = await logic.deleted_by_ids(["d1", "d2"], soft_delete=True)
    assert count == 2
    # 缓存清理完成
    assert "d1" not in logic.cache_repo._detail and "d2" not in logic.cache_repo._detail
    # Repo 标记软删除
    assert logic.repo._store["d1"].is_deleted is True
    assert logic.repo._store["d2"].is_deleted is True


@pytest.mark.asyncio
async def test_delete_by_id_hard_delete_and_clear_cache():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    logic.repo._store["dh"] = make_in_db("dh", "H")
    await logic.cache_repo.cache_detail(logic.repo._store["dh"].model_dump())

    count = await logic.delete_by_id("dh", soft_delete=False)
    assert count == 1
    assert "dh" not in logic.cache_repo._detail
    assert "dh" not in logic.repo._store  # 物理删除


@pytest.mark.asyncio
async def test_restore_by_ids_success_and_cache():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    logic.repo._store["r1"] = DummyInDB(id="r1", name="R1", is_deleted=True)
    logic.repo._store["r2"] = DummyInDB(id="r2", name="R2", is_deleted=True)

    res = await logic.restore_by_ids(["r1", "r2"])
    assert len(res) == 2
    assert all(x.id in ("r1", "r2") for x in res)
    # 缓存已回填
    assert logic.cache_repo._detail["r1"]["id"] == "r1"
    assert logic.cache_repo._detail["r2"]["id"] == "r2"
    # Repo 状态已恢复
    assert logic.repo._store["r1"].is_deleted is False
    assert logic.repo._store["r2"].is_deleted is False


@pytest.mark.asyncio
async def test_restore_by_id_not_found_raises():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    with pytest.raises(NotFoundError):
        await logic.restore_by_id("not-exist")


@pytest.mark.asyncio
async def test_restore_by_id_success_and_cache():
    logic = BaseLogic(repo=FakeRepo(), read_model=DummyRead, cache_repo=FakeCache())
    logic.repo._store["rx"] = DummyInDB(id="rx", name="RX", is_deleted=True)

    res = await logic.restore_by_id("rx")
    assert isinstance(res, DummyRead) and res.id == "rx"
    assert logic.cache_repo._detail["rx"]["id"] == "rx"
    assert logic.repo._store["rx"].is_deleted is False
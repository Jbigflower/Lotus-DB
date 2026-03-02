import pytest
import asyncio

from src.services.sync.base_sync_service import BaseSyncService


class FakeRepo:
    def __init__(self, fail_times: int = 0):
        self.upserts = []
        self.deletes = []
        self.snapshots = {}
        self.fail_times = fail_times
        self.attempts = 0

    async def upsert(self, objs):
        self.attempts += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("fail")
        self.upserts.extend(objs)

    async def delete(self, ids, soft=True):
        self.deletes.append((tuple(ids), soft))

    async def get_text_snapshot(self, _id):
        return self.snapshots.get(_id)

    async def save_text_snapshot(self, _id, text):
        self.snapshots[_id] = text


class SimpleModel:
    def __init__(self, _id: str, content: str = "", is_deleted: bool = False):
        self.id = _id
        self.content = content
        self.is_deleted = is_deleted


class FakeSyncService(BaseSyncService[SimpleModel]):
    TEXT_FIELDS = ["content"]

    def get_collection(self):
        return None

    def to_model_in_db(self, doc):
        return SimpleModel(str(doc.get("_id")), doc.get("content", ""), bool(doc.get("is_deleted", False)))

    def get_target_repo(self):
        return FakeRepo()

    def build_text(self, model):
        return None


class TextSyncService(BaseSyncService[SimpleModel]):
    TEXT_FIELDS = []

    def get_collection(self):
        return None

    def to_model_in_db(self, doc):
        return SimpleModel(str(doc.get("_id")), doc.get("content", ""), bool(doc.get("is_deleted", False)))

    def get_target_repo(self):
        return FakeRepo()

    def build_text(self, model):
        return model.content


@pytest.mark.asyncio
async def test_insert_triggers_upsert_and_snapshot():
    svc = TextSyncService()
    repo = FakeRepo()
    change = {
        "operationType": "insert",
        "fullDocument": {
            "_id": "n1",
            "content": "c",
            "is_deleted": False,
        },
    }
    await svc._handle_change(change, repo)
    assert repo.upserts and repo.upserts[0].id == "n1"
    assert repo.snapshots.get("n1") is not None


@pytest.mark.asyncio
async def test_update_skips_when_snapshot_same():
    svc = TextSyncService()
    repo = FakeRepo()
    doc = {
        "_id": "n2",
        "content": "c",
        "is_deleted": False,
    }
    model = svc.to_model_in_db(doc)
    same_text = svc.build_text(model)
    repo.snapshots[model.id] = same_text
    change = {"operationType": "update", "fullDocument": doc}
    await svc._handle_change(change, repo)
    assert not repo.upserts


@pytest.mark.asyncio
async def test_update_with_text_changed_upserts_and_saves_snapshot():
    svc = TextSyncService()
    repo = FakeRepo()
    doc = {
        "_id": "n3",
        "content": "c1",
        "is_deleted": False,
    }
    repo.snapshots["n3"] = "c0"
    change = {"operationType": "update", "fullDocument": doc}
    await svc._handle_change(change, repo)
    assert repo.upserts and repo.snapshots.get("n3") is not None


@pytest.mark.asyncio
async def test_delete_op_soft_delete():
    svc = TextSyncService()
    repo = FakeRepo()
    change = {"operationType": "delete", "documentKey": {"_id": "n4"}}
    await svc._handle_change(change, repo)
    assert repo.deletes and repo.deletes[0][0] == ("n4",)
    assert repo.deletes[0][1] is True


@pytest.mark.asyncio
async def test_flag_deleted_in_doc_soft_delete():
    svc = TextSyncService()
    repo = FakeRepo()
    change = {
        "operationType": "update",
        "fullDocument": {
            "_id": "n5",
            "content": "c",
            "is_deleted": True,
        },
    }
    await svc._handle_change(change, repo)
    assert repo.deletes and repo.deletes[0][0] == ("n5",)


@pytest.mark.asyncio
async def test_retry_upsert_on_failure(monkeypatch):
    svc = TextSyncService()
    repo = FakeRepo(fail_times=2)
    async def fast_sleep(_):
        return None
    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    change = {
        "operationType": "insert",
        "fullDocument": {
            "_id": "n6",
            "content": "c",
            "is_deleted": False,
        },
    }
    await svc._handle_change(change, repo)
    assert repo.attempts == 3
    assert repo.upserts and repo.upserts[0].id == "n6"


@pytest.mark.asyncio
async def test_semantic_change_with_text_fields_skip_and_upsert():
    svc = FakeSyncService()
    repo = FakeRepo()
    change_skip = {
        "operationType": "update",
        "fullDocument": {"_id": "s1", "content": "a", "is_deleted": False},
        "updateDescription": {"updatedFields": {"name": "x"}},
    }
    await svc._handle_change(change_skip, repo)
    assert not repo.upserts
    change_apply = {
        "operationType": "update",
        "fullDocument": {"_id": "s1", "content": "b", "is_deleted": False},
        "updateDescription": {"updatedFields": {"content": "b"}},
    }
    await svc._handle_change(change_apply, repo)
    assert repo.upserts and repo.upserts[0].id == "s1"
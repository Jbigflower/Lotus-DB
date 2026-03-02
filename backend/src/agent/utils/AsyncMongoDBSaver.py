from __future__ import annotations
from collections.abc import AsyncIterator, Sequence
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from contextlib import asynccontextmanager

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, UpdateOne

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.mongodb.utils import dumps_metadata, loads_metadata


async def _ensure_indexes(
    collection: AsyncIOMotorCollection,
    compound_index: list[tuple[str, int]],
    ttl: Optional[int] = None,
) -> None:
    def index_key_list(index: Any) -> list[tuple[str, int]]:
        if "key" in index:
            # motor returns key as list of tuples
            return list(index["key"])
        return []

    indexes = [idx async for idx in collection.list_indexes()]
    index_keys = [index_key_list(idx) for idx in indexes]
    if compound_index not in index_keys:
        await collection.create_index(compound_index, unique=True)
    if ttl is not None:
        ttl_index = [("created_at", ASCENDING)]
        found = False
        for idx in indexes:
            if index_key_list(idx) == ttl_index and idx.get("expireAfterSeconds") == ttl:
                found = True
                break
        if not found:
            await collection.create_index(ttl_index, expireAfterSeconds=ttl)


class AsyncMongoDBSaver(BaseCheckpointSaver):
    client: AsyncIOMotorClient
    db: AsyncIOMotorDatabase

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str = "checkpointing_db",
        checkpoint_collection_name: str = "checkpoints",
        writes_collection_name: str = "checkpoint_writes",
        ttl: Optional[int] = None,
        serde: SerializerProtocol | None = None,
        **_: Any,
    ) -> None:
        super().__init__()
        self.client = client
        self.db = self.client[db_name]
        self.checkpoint_collection: AsyncIOMotorCollection = self.db[checkpoint_collection_name]
        self.writes_collection: AsyncIOMotorCollection = self.db[writes_collection_name]
        self.ttl = ttl
        self._setup_lock = asyncio.Lock()
        self._setup_done = False
        if serde is not None:
            self.serde = serde
        else:
            self.serde = JsonPlusSerializer()

    async def setup(self) -> None:
        await _ensure_indexes(
            self.checkpoint_collection,
            [("thread_id", 1), ("checkpoint_ns", 1), ("checkpoint_id", -1)],
            self.ttl,
        )
        await _ensure_indexes(
            self.writes_collection,
            [
                ("thread_id", 1),
                ("checkpoint_ns", 1),
                ("checkpoint_id", -1),
                ("task_id", 1),
                ("idx", 1),
            ],
            self.ttl,
        )
        self._setup_done = True

    async def _ensure_setup(self) -> None:
        if self._setup_done:
            return
        async with self._setup_lock:
            if self._setup_done:
                return
            await self.setup()

    @classmethod
    @asynccontextmanager
    async def from_conn_string(
        cls,
        conn_string: Optional[str] = None,
        db_name: str = "checkpointing_db",
        checkpoint_collection_name: str = "checkpoints",
        writes_collection_name: str = "checkpoint_writes",
        ttl: Optional[int] = None,
        **kwargs: Any,
    ):
        client: Optional[AsyncIOMotorClient] = None
        try:
            client = AsyncIOMotorClient(conn_string)
            saver = AsyncMongoDBSaver(
                client,
                db_name=db_name,
                checkpoint_collection_name=checkpoint_collection_name,
                writes_collection_name=writes_collection_name,
                ttl=ttl,
                **kwargs,
            )
            await saver.setup()
            yield saver
        finally:
            if client:
                client.close()

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        await self._ensure_setup()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        if checkpoint_id := get_checkpoint_id(config):
            query = {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
            doc = await self.checkpoint_collection.find_one(query)
            if not doc:
                return None
        else:
            cursor = self.checkpoint_collection.find(
                {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}
            ).sort("checkpoint_id", -1).limit(1)
            doc = None
            async for d in cursor:
                doc = d
                break
            if not doc:
                return None

        config_values = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": doc["checkpoint_id"],
        }
        checkpoint = self.serde.loads_typed((doc["type"], doc["checkpoint"]))
        writes_cursor = self.writes_collection.find(config_values)
        pending_writes = []
        async for wrt in writes_cursor:
            pending_writes.append(
                (
                    wrt["task_id"],
                    wrt["channel"],
                    self.serde.loads_typed((wrt["type"], wrt["value"])),
                )
            )
        return CheckpointTuple(
            {"configurable": config_values},
            checkpoint,
            loads_metadata(self.serde, doc["metadata"]),
            (
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": doc.get("parent_checkpoint_id"),
                    }
                }
                if doc.get("parent_checkpoint_id")
                else None
            ),
            pending_writes,
        )

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        await self._ensure_setup()
        query: dict[str, Any] = {}
        if config is not None:
            if "thread_id" in config["configurable"]:
                query["thread_id"] = config["configurable"]["thread_id"]
            if "checkpoint_ns" in config["configurable"]:
                query["checkpoint_ns"] = config["configurable"]["checkpoint_ns"]
        if filter:
            for key, value in filter.items():
                query[f"metadata.{key}"] = dumps_metadata(self.serde, value)
        if before is not None:
            query["checkpoint_id"] = {"$lt": before["configurable"]["checkpoint_id"]}

        cursor = self.checkpoint_collection.find(
            query, limit=0 if limit is None else limit
        ).sort("checkpoint_id", -1)
        async for doc in cursor:
            config_values = {
                "thread_id": doc["thread_id"],
                "checkpoint_ns": doc["checkpoint_ns"],
                "checkpoint_id": doc["checkpoint_id"],
            }
            writes_cursor = self.writes_collection.find(config_values)
            pending_writes = []
            async for wrt in writes_cursor:
                pending_writes.append(
                    (
                        wrt["task_id"],
                        wrt["channel"],
                        self.serde.loads_typed((wrt["type"], wrt["value"])),
                    )
                )
            yield CheckpointTuple(
                config={"configurable": config_values},
                checkpoint=self.serde.loads_typed((doc["type"], doc["checkpoint"])),
                metadata=loads_metadata(self.serde, doc["metadata"]),
                parent_config=(
                    {
                        "configurable": {
                            "thread_id": doc["thread_id"],
                            "checkpoint_ns": doc["checkpoint_ns"],
                            "checkpoint_id": doc.get("parent_checkpoint_id"),
                        }
                    }
                    if doc.get("parent_checkpoint_id")
                    else None
                ),
                pending_writes=pending_writes,
            )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        await self._ensure_setup()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        checkpoint_id = checkpoint["id"]
        type_, serialized_checkpoint = self.serde.dumps_typed(checkpoint)
        metadata = metadata.copy()
        metadata.update(config.get("metadata", {}))
        doc: dict[str, Any] = {
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "type": type_,
            "checkpoint": serialized_checkpoint,
            "metadata": dumps_metadata(self.serde, metadata),
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
        }
        if self.ttl:
            doc["created_at"] = datetime.now(tz=timezone.utc)

        await self.checkpoint_collection.update_one(
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id},
            {"$set": doc},
            upsert=True,
        )
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self._ensure_setup()
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"]["checkpoint_ns"]
        checkpoint_id = config["configurable"]["checkpoint_id"]
        set_method = "$set" if all(w[0] in WRITES_IDX_MAP for w in writes) else "$setOnInsert"
        operations = []
        now = datetime.now(tz=timezone.utc)
        for idx, (channel, value) in enumerate(writes):
            upsert_query = {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "task_path": task_path,
                "idx": WRITES_IDX_MAP.get(channel, idx),
            }
            type_, serialized_value = self.serde.dumps_typed(value)
            update_doc: dict[str, Any] = {
                "channel": channel,
                "type": type_,
                "value": serialized_value,
            }
            if self.ttl:
                update_doc["created_at"] = now
            operations.append(
                UpdateOne(
                    filter=upsert_query,
                    update={set_method: update_doc},
                    upsert=True,
                )
            )
        if operations:
            await self.writes_collection.bulk_write(operations)

    async def adelete_thread(self, thread_id: str) -> None:
        await self._ensure_setup()
        await self.checkpoint_collection.delete_many({"thread_id": thread_id})
        await self.writes_collection.delete_many({"thread_id": thread_id})

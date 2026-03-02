from contextlib import contextmanager, asynccontextmanager
from langgraph.store.base import BaseStore
from motor.motor_asyncio import AsyncIOMotorClient

class MongoDBStore(BaseStore):
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.client = client
        self.collection = self.client[db_name]["user_memories"]

    async def get(self, namespace: tuple, key: str):
        doc = await self.collection.find_one({"namespace": namespace, "key": key})
        return doc["value"] if doc else None

    async def put(self, namespace: tuple, key: str, value: dict):
        await self.collection.update_one(
            {"namespace": namespace, "key": key},
            {"$set": {"value": value}},
            upsert=True
        )

    @contextmanager
    def batch(self):
        yield self

    @asynccontextmanager
    async def abatch(self):
        yield self

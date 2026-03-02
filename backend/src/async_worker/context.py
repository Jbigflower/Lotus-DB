from src.core.database import init_databases, close_databases


async def init_resources():
    await init_databases()


async def close_resources():
    await close_databases()

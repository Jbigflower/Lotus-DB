import asyncio
from src.async_worker.main import main as start_entry

if __name__ == "__main__":
    asyncio.run(start_entry())

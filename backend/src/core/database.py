from src.db.mongo_db import init_mongo, close_mongo
from src.db.lance_db import init_lance, close_lance
from src.db.redis_db import init_redis, close_redis
from config.logging import get_logger

logger = get_logger(__name__)


async def init_databases():
    await init_mongo()
    logger.info(f"mongo db 初始化 成功！")
    await init_lance()
    logger.info(f"lance db 初始化 成功！")
    await init_redis()
    logger.info(f"redis db 初始化 成功！")


async def close_databases():
    await close_mongo()
    logger.info(f"mongo db 关闭 成功！")
    await close_lance()
    logger.info(f"lance db 关闭 成功！")
    await close_redis()
    logger.info(f"redis db 关闭 成功！")

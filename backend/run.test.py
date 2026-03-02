import asyncio
from config.logging import get_logger, configure_logging, log_function

configure_logging()

logger = get_logger(__name__)

logger.debug("这是一条调试日志")
logger.info("这是一条信息日志")
b = 1 / 0


@log_function(level="info")
def test_func(a, b):
    return a / b


@log_function()
async def async_test(x):
    await asyncio.sleep(0.1)
    return 10 / x


@log_function()
def error_func(x):
    return 10 / x


test_func(5, 2)
asyncio.run(async_test(2))
error_func(0)

# src/client/ollama_embedding_client.py
from ollama import AsyncClient
from config.logging import get_logger
from typing import List, AsyncGenerator
import asyncio
import os
from async_lru import alru_cache

logger = get_logger(__name__)


async def _example():
    resp = await AsyncClient().chat(
        model="gemma3", messages=[{"role": "user", "content": "hello"}]
    )
    # 或者 embed 的异步版
    resp2 = await AsyncClient().embed(model="some_model", input=["文本1", "文本2"])


class EmbeddingClient:
    def __init__(
        self,
        host: str = None,
        model_name: str = None,
        out_dim: int = 768,
        batch_size: int = 32,
        request_timeout: int = 15,
    ):
        if host:
            self.client = AsyncClient(host=host)
        else:
            self.client = AsyncClient()
        self.model_name = model_name
        self.out_dim = out_dim
        self.batch_size = batch_size  # TODO 加到环境变量中
        self.request_timeout = request_timeout

        logger.info(f"初始化 EmbeddingClient，host: {host}, model_name: {model_name}")

    # @alru_cache(maxsize=1024)  # Removed cache to avoid unhashable type 'list' error
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        resp = await self.client.embed(model=self.model_name, input=texts)
        logger.info(
            f"传入{texts[0][: min(5, len(texts[0]))]}...处理完成, 耗时{resp.total_duration / 1_000_000}ms"
        )
        return resp["embeddings"]


embedding_client = None


async def init_embedding_client() -> EmbeddingClient:
    """
    初始化异步的 embedding 客户端
    Python 的全局变量赋值是原子操作，但 多协程同时初始化 有可能出现短暂竞争（即可能会短时间内同时创建两个实例，但最终全局变量只会保留最后赋值的那个
    Returns:
        EmbeddingClient: 初始化后的 embedding 客户端
    """
    # 自动设置 NO_PROXY 以避免 localhost 代理问题
    if not os.environ.get("NO_PROXY"):
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"
        logger.info("已自动设置 NO_PROXY=localhost,127.0.0.1 以避免 Ollama 连接 503 错误")

    global embedding_client
    if embedding_client is None:
        from config.setting import settings

        embedding_client = EmbeddingClient(
            settings.llm.ollama_base_url,
            settings.llm.ollama_embedding_model,
            settings.llm.ollama_embedding_dim,
        )
        # 加一条测试，看看输出维度和设定维度是否相同
        test_text = "这是一条测试文本"
        test_embedding = await embedding_client.embed_texts([test_text])
        if len(test_embedding[0]) != embedding_client.out_dim:
            raise ValueError(
                f"当前模型为{settings.llm.ollama_embedding_model}输出维度与设定维度不一致，输出维度为{len(test_embedding[0])}，设定维度为{embedding_client.out_dim}"
            )
    return embedding_client


async def get_text_embedding_async(texts: List[str]) -> List[List[float]]:
    """
    异步调用 embedding model 生成 embedding
    Args:
        text (List[str]): 待生成 embedding 的文本列表
    Returns:
        List[List[float]]: 生成的 embedding 向量列表，每个向量对应输入文本列表中的一个文本
    """
    # 获取 embedding 客户端
    global embedding_client
    if embedding_client is None:
        await init_embedding_client()

    # 调用客户端方法生成 embedding
    try:
        vectors = await asyncio.wait_for(
            embedding_client.embed_texts(texts), timeout=embedding_client.request_timeout
        )
    except asyncio.TimeoutError:
        logger.error("调用 embedding model 超时")  # TODO：增加超时处理
        return [[0.0] * embedding_client.out_dim for _ in texts]
    return vectors


async def iter_get_text_embedding(
    texts: List[str],
) -> AsyncGenerator[tuple[int, List[List[float]]], None]:
    """
    异步调用 embedding model 生成 embedding
    Args:
        texts (List[str]): 待生成 embedding 的文本列表
    Yields:
        (batch_start_index, vectors): 批次起始下标 + embedding 向量列表
    """
    # 获取 embedding 客户端
    global embedding_client
    if embedding_client is None:
        await init_embedding_client()

    BATCH_SIZE = embedding_client.batch_size
    TIMEOUT = embedding_client.request_timeout

    batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    logger.info(f"共{len(texts)}条数据，分{len(batches)}批次处理")

    for i, batch_texts in enumerate(batches):
        try:
            vectors = await asyncio.wait_for(
                embedding_client.embed_texts(batch_texts), timeout=TIMEOUT
            )
            logger.info(f"批次 {i + 1}/{len(batches)} 完成")
            yield i * BATCH_SIZE, vectors
        except asyncio.TimeoutError:
            logger.error(f"批次 {i + 1}/{len(batches)} 超时")
            yield i * BATCH_SIZE, [[0.0] * embedding_client.out_dim for _ in batch_texts]
        except Exception as e:
            logger.error(f"批次 {i + 1}/{len(batches)} 异常: {e}")
            yield i * BATCH_SIZE, [[0.0] * embedding_client.out_dim for _ in batch_texts]

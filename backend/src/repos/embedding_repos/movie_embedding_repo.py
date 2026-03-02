from typing import Dict, Any, List, Optional
from lancedb.pydantic import Vector, LanceModel  # 导入LanceDB Pydantic相关类
from pydantic import BaseModel
from src.models import MovieInDB
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo
from src.clients.ollama_embedding_client import (
    get_text_embedding_async,
    iter_get_text_embedding,
)
from config.logging import get_logger
from config.setting import settings

logger = get_logger(__name__)

MOVIE_EMBEDDING_DIM = settings.llm.ollama_embedding_dim


class MovieSchema(LanceModel):
    """电影向量化数据模型，定义LanceDB表结构"""

    id: str  # 主键（关联MovieInDB的id，唯一标识）
    vector: Vector(
        MOVIE_EMBEDDING_DIM
    )  # 向量字段：dim需与你的embedding模型维度一致（如Ollama默认768）
    document: str  # 用于生成向量的电影文本描述（原Chroma的document）
    library_id: str  # 电影库ID（元数据）
    title: str  # 电影标题（元数据）
    is_deleted: bool  # 软删除标记（父类依赖此字段）


class MovieChunk(BaseModel):
    id: str
    parent_id: str
    library_id: str
    title: str
    content: str
    is_deleted: bool = False
    score: Optional[float] = None


class MovieEmbeddingRepo(BaseLanceRepo):
    """电影向量化仓储层：支持添加、更新、搜索、软删除（适配LanceDB）"""

    def __init__(self):
        # 1. 修正父类参数：LanceDB用table_name，而非collection_name
        super().__init__(table_name="movies")

    # -------------------------- 核心：LanceDB表结构定义（必须实现） --------------------------
    def get_schema(self) -> type[LanceModel]:
        """定义LanceDB表结构，需与to_lance_record的输出字段对应"""
        return MovieSchema

    # -------------------------- 工具：构建电影文本描述 --------------------------
    def _build_document_text(self, movie: MovieInDB) -> str:
        """将电影结构化信息转成语义描述，用于生成embedding"""
        directors = ", ".join(movie.directors) if movie.directors else "未知导演"
        actors = ", ".join(movie.actors[:5]) if movie.actors else "未知演员"
        genres = ", ".join(movie.genres) if movie.genres else "未知类型"
        tags = ", ".join(movie.tags) if movie.tags else "无用户标签"
        rating = f"{movie.rating:.1f}" if movie.rating is not None else "暂无评分"

        text = (
            f"电影《{movie.title_cn or movie.title}》({movie.title}) "
            f"是由 {directors} 执导，{actors} 主演的 {genres} 电影，"
            f"上映于 {movie.release_date or '未知日期'}。"
            f"该影片描述了：{movie.description_cn or movie.description or '无描述'}。"
            f"用户认为它属于 {tags} 类电影，并给予 {rating} 分的评价。"
        )
        return text

    # -------------------------- 抽象方法：单条记录转换（适配LanceDB） --------------------------
    async def to_lance_record(self, movie: MovieInDB) -> Dict[str, Any]:
        """将MovieInDB转换为LanceDB可插入的记录（平级字段，无metadata嵌套）"""
        try:
            logger.info(f"[TO LANCE RECORD] Start processing movie: {movie.id}")
            # 生成文本描述和embedding
            document = self._build_document_text(movie)
            embedding = (await get_text_embedding_async([document]))[0]
            logger.info(f"[TO LANCE RECORD] Embedding generated for movie: {movie.id}")

            # 2. LanceDB记录：字段与get_schema定义完全对应，无嵌套metadata
            return {
                "id": movie.id,
                "vector": embedding,
                "document": document,
                "library_id": movie.library_id,
                "title": movie.title,
                "is_deleted": False,  # 新记录默认未删除
            }

        except Exception as e:
            logger.error(f"[TO LANCE RECORD] 向量化失败: {e}, 电影ID={movie.id}")
            raise

    # -------------------------- 抽象方法：批量记录转换（必须实现） --------------------------
    async def batch_to_lance_records(
        self, movies: List[MovieInDB]
    ) -> List[Dict[str, Any]]:
        """
        批量将MovieInDB转换为LanceDB记录
        优化点：先批量构建文本，再用iter_get_text_embedding批量生成embedding，减少接口调用次数
        """
        if not movies:
            return []

        # 1. 批量构建所有电影的文本描述（与movies列表下标一一对应）
        texts = []
        movie_info_list = []  # 暂存电影基础信息，避免后续重复取属性
        for movie in movies:
            logger.info(f"[BATCH TO LANCE RECORD] Processing movie: {movie.id}")
            text = self._build_document_text(movie)
            texts.append(text)
            # 暂存后续组装记录需要的基础信息（与texts下标对齐）
            movie_info_list.append(
                {
                    "id": movie.id,
                    "library_id": movie.library_id,
                    "title": movie.title,
                }
            )
        logger.info(
            f"批量处理电影数量：{len(movies)}，待生成embedding文本数量：{len(texts)}"
        )

        # 2. 用批量embedding接口生成向量，按批次接收结果
        # 初始化向量列表（默认填充0向量，避免下标错位）
        vectors = [
            [0.0] * MOVIE_EMBEDDING_DIM for _ in texts
        ]  # 需确保embedding_client已初始化
        async for batch_start_idx, batch_vectors in iter_get_text_embedding(texts):
            # 计算当前批次在总列表中的下标范围
            batch_end_idx = batch_start_idx + len(batch_vectors)
            # 将当前批次向量写入总向量列表（按起始下标对齐）
            vectors[batch_start_idx:batch_end_idx] = batch_vectors
            logger.info(
                f"已处理embedding批次，起始下标：{batch_start_idx}，向量数量：{len(batch_vectors)}"
            )

        # 3. 批量组装LanceDB记录（文本、向量、基础信息下标一一对应）
        records = []
        for idx, (movie_info, vector, text) in enumerate(
            zip(movie_info_list, vectors, texts)
        ):
            # 检查向量是否有效（避免全0向量，可选：根据业务决定是否过滤）
            if all(v == 0.0 for v in vector):
                logger.warning(
                    f"电影ID {movie_info['id']} 的embedding为全0向量，可能生成失败"
                )

            records.append(
                {
                    "id": movie_info["id"],
                    "vector": vector,
                    "document": text,
                    "library_id": movie_info["library_id"],
                    "title": movie_info["title"],
                    "is_deleted": False,
                }
            )

        logger.info(f"批量生成LanceDB记录完成，共 {len(records)} 条")
        return records

    # -------------------------- 抽象方法：从LanceDB记录还原对象 --------------------------
    def from_lance_record(self, record: Dict[str, Any]) -> MovieChunk:
        """将LanceDB查询结果还原为MovieChunk对象（含向量、文档等字段）"""
        try:
            return MovieChunk(
                id=record["id"],
                parent_id=record["id"],
                library_id=record["library_id"],
                title=record["title"],
                content=record["document"],
                is_deleted=record.get("is_deleted", False),
                score=record.get("score"),
            )
        except Exception as e:
            logger.error(
                f"[FROM LANCE RECORD] 解析记录失败: {e}, 电影ID={record.get('id')}"
            )
            raise

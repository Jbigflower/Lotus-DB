"""
Lotus-DB Repository Layer
提供完整的数据访问层实现，包括 MongoDB、Redis 缓存和向量数据库
"""

# MongoDB Repository Layer
from .mongo_repos import (
    BaseRepo,
    MovieRepo,
    AssetRepo,
    LibraryRepo,
    UserRepo,
    UserCustomListRepo,
    UserAssetRepo,
    WatchHistoryRepo,
    TaskRepo,
)

# Redis Cache Repository Layer
from .cache_repos import (
    BaseRedisRepo,
    MovieRedisRepo,
    AssetRedisRepo,
    LibraryRedisRepo,
    UserRedisRepo,
    WatchHistoryRedisRepo,
    UserAssetRedisRepo,
    UserCustomListRedisRepo,
    TaskRedisRepo,
)

# Embedding Repository Layer
from .embedding_repos import (
    BaseChromaRepo,
    BaseLanceRepo,
    MovieEmbeddingRepo,
    NoteEmbeddingRepo,
    SubtitleEmbeddingRepo,
)

__all__ = [
    # MongoDB Repositories
    "BaseRepo",
    "MovieRepo",
    "AssetRepo",
    "LibraryRepo",
    "UserRepo",
    "UserCustomListRepo",
    "UserAssetRepo",
    "WatchHistoryRepo",
    "TaskRepo",
    # Redis Cache Repositories
    "BaseRedisRepo",
    "MovieRedisRepo",
    "AssetRedisRepo",
    "LibraryRedisRepo",
    "UserRedisRepo",
    "WatchHistoryRedisRepo",
    "UserAssetRedisRepo",
    "UserCustomListRedisRepo",
    "TaskRedisRepo",
    # Embedding Repositories
    "BaseChromaRepo",
    "BaseLanceRepo",
    "MovieEmbeddingRepo",
    "NoteEmbeddingRepo",
    "SubtitleEmbeddingRepo",
]

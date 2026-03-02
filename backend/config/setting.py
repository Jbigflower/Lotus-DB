"""
Lotus-DB 系统配置模块

使用 Pydantic v2.11 BaseSettings 进行配置管理
支持从环境变量和 .env 文件读取配置
"""

import os
from typing import Any, Optional, List
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict, BaseSettings


class LotusBaseSettings(BaseSettings):
    """基础配置类，包含通用的 .env 加载配置"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


class DatabaseSettings(LotusBaseSettings):
    """数据库配置"""

    # MongoDB 配置
    mongo_host: str = Field(default="localhost", description="MongoDB 主机地址")
    mongo_port: int = Field(default=27017, description="MongoDB 端口")
    mongo_db: str = Field(default="lotus_db", description="MongoDB 数据库名")
    mongo_username: Optional[str] = Field(default=None, description="MongoDB 用户名")
    mongo_password: Optional[str] = Field(default=None, description="MongoDB 密码")
    mongo_auth_source: str = Field(default="admin", description="MongoDB 认证数据库")
    mongo_replica_set: Optional[str] = Field(
        default="rs0", description="MongoDB 副本集名称"
    )

    # Redis 配置
    redis_host: str = Field(default="localhost", description="Redis 主机地址")
    redis_port: int = Field(default=6379, description="Redis 端口")
    redis_db: int = Field(default=0, description="Redis 数据库编号")
    redis_password: Optional[str] = Field(default=None, description="Redis 密码")
    redis_max_connections: int = Field(default=10, description="Redis 最大连接数")

    # Chroma 配置
    chroma_host: str = Field(default="localhost", description="Chroma 主机地址")
    chroma_port: int = Field(default=8000, description="Chroma 端口")
    chroma_persist_directory: str = Field(
        default="./data/chroma_data", description="Chroma 持久化目录"
    )
    chroma_collection_name: str = Field(
        default="lotus_vectors", description="Chroma 集合名称"
    )

    # LanceDB 配置
    lancedb_path: str = Field(
        default="./data/lance_data", description="LanceDB 数据目录"
    )
    lance_db_name: str = Field(default="lotus_db", description="LanceDB 数据库名")

    @property
    def mongo_url(self) -> str:
        """构建 MongoDB 连接 URL"""
        if self.mongo_username and self.mongo_password:
            auth = f"{self.mongo_username}:{self.mongo_password}@"
        else:
            auth = ""

        replica_set = (
            f"?replicaSet={self.mongo_replica_set}" if self.mongo_replica_set else ""
        )
        return f"mongodb://{auth}{self.mongo_host}:{self.mongo_port}/{self.mongo_db}{replica_set}"

    @property
    def redis_url(self) -> str:
        """构建 Redis 连接 URL"""
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def chroma_url(self) -> str:
        """构建 Chroma 连接 URL"""
        return f"http://{self.chroma_host}:{self.chroma_port}"


class AppSettings(LotusBaseSettings):
    """应用程序配置"""

    # 应用基础配置
    app_name: str = Field(default="Lotus-DB", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    debug: bool = Field(default=False, description="调试模式")
    environment: str = Field(default="development", description="运行环境")
    # 新增：服务器名称与首选语言（支持 .env 动态修改）
    server_name: str = Field(default="Lotus-Server", description="服务器名称")
    preferred_language: str = Field(default="zh-CN", description="首选语言")

    # 管理员默认配置
    admin_username: str = Field(default="admin", description="默认管理员用户名")
    admin_password: str = Field(default="admin123", description="默认管理员密码")

    # API 配置
    api_prefix: str = Field(default="/api/v1", description="API 路径前缀")
    host: str = Field(default="0.0.0.0", description="服务器主机")
    port: int = Field(default=8000, description="服务器端口")
    reload: bool = Field(default=True, description="自动重载")

    # 安全配置
    secret_key: str = Field(
        default="your-secret-key-change-in-production", description="JWT 密钥"
    )
    algorithm: str = Field(default="HS256", description="JWT 算法")
    access_token_expire_minutes: int = Field(
        default=3000, description="访问令牌过期时间（分钟）"
    )

    # CORS 配置 - 注意：使用 Any 类型以支持从 .env 读取字符串列表
    cors_origins: Any = Field(default=["*"], description="CORS 允许的源")
    cors_methods: Any = Field(default=["*"], description="CORS 允许的方法")
    cors_headers: Any = Field(default=["*"], description="CORS 允许的头部")

    @field_validator("cors_origins", "cors_methods", "cors_headers", mode="before")
    @classmethod
    def parse_cors_list(cls, v):
        """解析 CORS 配置列表"""
        if isinstance(v, str):
            # 从环境变量读取的字符串，按逗号分割
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class PerformanceSettings(LotusBaseSettings):
    """性能配置"""

    # 查询限制
    max_query_limit: int = Field(default=1000, description="一次查询上限")
    max_batch_size: int = Field(default=100, description="批量操作上限")
    max_concurrent_requests: int = Field(default=50, description="最大并发请求数")

    # 缓存配置
    cache_ttl_seconds: int = Field(default=300, description="缓存过期时间（秒）")
    cache_max_size: int = Field(default=10000, description="缓存最大条目数")

    # 超时配置
    db_query_timeout: int = Field(default=30, description="数据库查询超时时间（秒）")
    external_api_timeout: int = Field(default=60, description="外部 API 请求超时时间（秒）")


class MediaSettings(LotusBaseSettings):
    """媒体文件配置"""

    # 存储路径配置
    library_prefix: str = Field(default="./data/main", description="媒体库根路径前缀")
    user_prefix: str = Field(default="./data/user", description="用户媒体路径前缀")
    other_prefix: str = Field(default="./data/others", description="其他媒体路径前缀")

    # 文件大小限制（字节）
    max_file_size: int = Field(
        default=100 * 1024 * 1024, description="最大文件大小（100MB）"
    )
    max_video_size: int = Field(
        default=5 * 1024 * 1024 * 1024, description="最大视频文件大小（5GB）"
    )

    # 支持的文件类型 - 使用 Any 类型
    allowed_video_extensions: Any = Field(
        default=[".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        description="允许的视频文件扩展名",
    )
    allowed_image_extensions: Any = Field(
        default=[".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
        description="允许的图片文件扩展名",
    )
    allowed_subtitle_extensions: Any = Field(
        default=[".srt", ".ass", ".ssa", ".vtt"], description="允许的字幕文件扩展名"
    )

    # 静态分发与签名配置（FastAPI -> Nginx）
    nginx_static_base_url: str = Field(
        default="http://localhost:8080",
        description="Nginx 静态资源基础域名/端口"
    )
    nginx_library_location: str = Field(
        default="/static/library",
        description="Nginx 对应库资源的公开路径前缀（alias 到 library_prefix）"
    )
    nginx_user_location: str = Field(
        default="/static/user",
        description="Nginx 对应用户资源的公开路径前缀（alias 到 user_prefix）"
    )
    secure_link_secret: str = Field(
        default="change-me",
        description="用于 ngx_http_secure_link_module 的签名密钥（需与 Nginx 配置一致）"
    )
    secure_link_ttl_seconds: int = Field(
        default=300,
        description="签名链接有效期（秒）"
    )
    secure_link_param_signature: str = Field(
        default="st",
        description="签名参数名（与 Nginx secure_link 对应）"
    )
    secure_link_param_expires: str = Field(
        default="e",
        description="过期时间参数名（与 Nginx secure_link 对应）"
    )

    @field_validator(
        "allowed_video_extensions",
        "allowed_image_extensions",
        "allowed_subtitle_extensions",
        mode="before",
    )
    @classmethod
    def parse_extension_list(cls, v):
        """解析文件扩展名列表"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class LLMSettings(LotusBaseSettings):
    """LLM 与 Agent 增强配置"""
    
    # DeepSeek 配置
    deepseek_api_key: Optional[str] = Field(
        default=None, description="DeepSeek API 密钥"
    )
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1", description="DeepSeek API 基础 URL"
    )
    deepseek_model: str = Field(
        default="deepseek-chat", description="DeepSeek 模型名称"
    )

    # Ollama 配置
    ollama_base_url: str = Field(
        default="http://localhost:11434", description="Ollama API 基础 URL"
    )
    ollama_embedding_model: str = Field(
        default="qwen3-embedding:0.6b", description="Ollama 模型名称"
    )
    ollama_embedding_dim: int = Field(default=1024, description="Ollama 嵌入维度")

    # 通用 LLM 配置
    default_temperature: float = Field(default=0.7, description="默认温度参数")
    default_max_tokens: int = Field(default=2048, description="默认最大令牌数")
    request_timeout: int = Field(default=60, description="请求超时时间（秒）")

    # langchain
    langraph_db_name: str = Field(default="langgraph_chat", description="LangGraph 状态数据库名称")
    langsmith_tracing: bool = Field(default=True, description="是否启用 LangSmith 跟踪")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com", description="LangSmith 端点")
    langsmith_api_key: str = Field(default=None, description="LangSmith API 密钥")
    langsmith_project: str = Field(default="lotus-db", description="LangSmith 项目名称")

    # 搜索配置
    tavily_use: bool = Field(default=True, description="是否启用 Tavily 搜索")
    tavily_api_key: Optional[str] = Field(
        default=None, description="Tavily API 密钥"
    )
    # Augment 开关 (Feature Flags)
    enable_augment: bool = Field(default=True, description="是否启用 Augment 增强模式")
    use_skills: bool = Field(default=True, description="是否启用 Skills 按需加载 (False 则全量注入)")
    enable_context_compression: bool = Field(default=True, description="是否启用上下文压缩")
    enable_safety_guardrails: bool = Field(default=True, description="是否启用安全门控")
    
    # 阈值配置
    compression_threshold: float = Field(default=0.7, description="触发压缩的 Token 比例阈值 (0.0-1.0)")


class PluginSettings(LotusBaseSettings):
    """插件配置"""

    # 插件开关
    enabled: bool = Field(default=True, description="是否启用插件")

    omdb_api_key: Optional[str] = Field(
        default=None, description="OMDB API 密钥"
    )

class Settings(LotusBaseSettings):
    """主配置类，聚合所有配置"""

    # 插件配置
    plugins: PluginSettings = Field(default_factory=PluginSettings)

    # 子配置
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    media: MediaSettings = Field(default_factory=MediaSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化子配置，确保它们也能读取环境变量
        self.database = DatabaseSettings()
        self.app = AppSettings()
        self.media = MediaSettings()
        self.llm = LLMSettings()
        self.performance = PerformanceSettings()
        self.plugins = PluginSettings()


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例（用于依赖注入）"""
    return settings
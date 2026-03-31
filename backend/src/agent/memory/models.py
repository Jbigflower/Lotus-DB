from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional
from uuid import uuid4


class MemoryTier(str, Enum):
    """记忆层级枚举。"""

    AGENT = "agent"
    USER = "user"
    SESSION = "session"


class MemoryCategory(str, Enum):
    """记忆类别枚举。"""

    FACT = "fact"   # 事实
    PREFERENCE = "preference"   # 偏好
    BEHAVIOR = "behavior"   # 行为
    CORRECTION = "correction"   # 修正
    KNOWLEDGE = "knowledge"   # 知识


class MemoryStatus(str, Enum):
    """记忆生命周期状态枚举。"""

    ACTIVE = "active"   # 活动
    SUPERSEDED = "superseded"   # 被替代
    ARCHIVED = "archived"   # 归档


@dataclass
class MemoryItem:
    """记忆项数据模型。"""

    memory_id: str = field(default_factory=lambda: str(uuid4()))
    tier: MemoryTier = MemoryTier.USER
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    category: MemoryCategory = MemoryCategory.FACT
    content: str = ""
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.5
    source_type: Literal["extracted", "stated", "curated"] = "extracted"   # 来源类型：提取、陈述、整理
    source_turn_ids: List[str] = field(default_factory=list)   # 来源轮次 ID 列表
    created_at: datetime = field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=datetime.now(timezone.utc))
    last_accessed_at: datetime = field(default_factory=datetime.now(timezone.utc))   # 最后访问时间 
    access_count: int = 0   # 访问次数
    status: MemoryStatus = MemoryStatus.ACTIVE   # 记忆生命周期状态
    superseded_by: Optional[str] = None   # 被替代的记忆 ID
    embedding: Optional[List[float]] = None   # 向量表示

    def to_dict(self) -> Dict[str, Any]:
        """转换为可持久化的字典。"""

        return {
            "memory_id": self.memory_id,
            "tier": self.tier.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "category": self.category.value,
            "content": self.content,
            "entities": list(self.entities),
            "confidence": self.confidence,
            "source_type": self.source_type,
            "source_turn_ids": list(self.source_turn_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "status": self.status.value,
            "superseded_by": self.superseded_by,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryItem":
        """从字典构造记忆项。"""

        payload = dict(data)
        payload.pop("_id", None)
        return cls(
            memory_id=str(payload.get("memory_id", str(uuid4()))),
            tier=MemoryTier(payload.get("tier", MemoryTier.USER.value)),
            user_id=payload.get("user_id"),
            session_id=payload.get("session_id"),
            category=MemoryCategory(payload.get("category", MemoryCategory.FACT.value)),
            content=payload.get("content", ""),
            entities=list(payload.get("entities") or []),
            confidence=float(payload.get("confidence", 0.5)),
            source_type=payload.get("source_type", "extracted"),
            source_turn_ids=list(payload.get("source_turn_ids") or []),
            created_at=_parse_datetime(payload.get("created_at")),
            updated_at=_parse_datetime(payload.get("updated_at")),
            last_accessed_at=_parse_datetime(payload.get("last_accessed_at")),
            access_count=int(payload.get("access_count", 0)),
            status=MemoryStatus(payload.get("status", MemoryStatus.ACTIVE.value)),
            superseded_by=payload.get("superseded_by"),
            embedding=payload.get("embedding"),
        )


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)

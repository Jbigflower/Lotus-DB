from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from ..llm.provider import LLMClient
from .models import MemoryItem, MemoryStatus, MemoryTier
from .store import MemoryStoreFacade


class ConflictDecision(BaseModel):
    """冲突判断结果。"""

    action: str = Field(..., description="refinement | contradiction | independent")


@dataclass
class ConflictResolver:
    """记忆冲突解决器。"""

    store: MemoryStoreFacade
    llm_client: LLMClient
    embedding_fn: Callable[[str], Awaitable[List[float]]]
    duplicate_threshold: float = 0.92
    conflict_zone_low: float = 0.6
    conflict_zone_high: float = 0.92

    async def resolve_and_store(self, new_item: MemoryItem) -> None:
        """检测冲突并写入记忆。"""

        new_item.embedding = await self.embedding_fn(new_item.content)
        candidates = await self.store.search_semantic(
            query_embedding=new_item.embedding,
            tier=new_item.tier,
            user_id=new_item.user_id,
            status=MemoryStatus.ACTIVE,
            top_k=5,
        )
        for existing in candidates:
            similarity = getattr(existing, "similarity_score", 0.0)
            if similarity >= self.duplicate_threshold:
                await self.store.touch(existing.memory_id)
                return
            if self.conflict_zone_low < similarity < self.conflict_zone_high:
                relation = await self._classify_relation(existing, new_item)
                if relation == "refinement":
                    existing.content = new_item.content
                    existing.confidence = max(existing.confidence, new_item.confidence)
                    existing.entities = list({*existing.entities, *new_item.entities})
                    existing.updated_at = datetime.now(timezone.utc)
                    await self.store.update(existing)
                    return
                if relation == "contradiction":
                    await self.store.update_status(
                        existing.memory_id,
                        MemoryStatus.SUPERSEDED,
                        superseded_by=new_item.memory_id,
                    )
                    break
        await self.store.add(new_item)

    async def _classify_relation(self, existing: MemoryItem, new: MemoryItem) -> str:
        prompt = (
            "判断两条记忆的关系，只能输出 refinement / contradiction / independent。\n"
            f"记忆A（已有）: {existing.content}\n"
            f"记忆B（新增）: {new.content}\n"
        )
        response = await self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        if not response.content:
            return "independent"
        try:
            content = _clean_json_content(response.content)
            payload = json.loads(content)
            decision = ConflictDecision.model_validate(payload)
            return decision.action.strip().lower()
        except Exception:
            return response.content.strip().lower()


def _clean_json_content(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()

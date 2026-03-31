from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol

from pydantic import BaseModel, Field

from ..llm.provider import LLMClient
from .models import MemoryCategory, MemoryItem, MemoryTier
from .store import MemoryStoreFacade

from config.logging import get_logic_logger

logger = get_logic_logger("lotus-agent:memory_extraction")


class ConflictResolverProtocol(Protocol):
    """冲突解决器协议。"""

    async def resolve_and_store(self, item: MemoryItem) -> None:
        """处理冲突并写入存储。"""


class ExtractedMemory(BaseModel):
    """LLM 提取的结构化记忆项。"""

    category: str = Field(..., description="记忆类别")
    content: str = Field(..., description="记忆内容")
    confidence: str = Field(..., description="置信度")
    source_turn_id: str = Field(..., description="来源轮次 ID")
    entities: List[str] = Field(default_factory=list, description="实体列表")

    def to_memory_item(self, *, user_id: str, session_id: str) -> Optional[MemoryItem]:
        """转换为 MemoryItem。"""
        raw = self.category.strip().lower()
        mapping = {
            "偏好": MemoryCategory.PREFERENCE,
            "事实": MemoryCategory.FACT,
            "行为": MemoryCategory.BEHAVIOR,
            "纠正": MemoryCategory.CORRECTION,
            "更正": MemoryCategory.CORRECTION,
        }
        if raw in mapping:
            category = mapping[raw]
        elif "偏好" in raw:
            category = MemoryCategory.PREFERENCE
        elif "事实" in raw:
            category = MemoryCategory.FACT
        elif "行为" in raw:
            category = MemoryCategory.BEHAVIOR
        elif "纠正" in raw or "更正" in raw:
            category = MemoryCategory.CORRECTION
        else:
            try:
                category = MemoryCategory(raw)
            except ValueError:
                return None
        confidence = _map_confidence(self.confidence)
        return MemoryItem(
            tier=MemoryTier.USER,
            user_id=user_id,
            session_id=session_id,
            category=category,
            content=self.content.strip(),
            entities=self.entities,
            confidence=confidence,
            source_type="extracted",
            source_turn_ids=[self.source_turn_id],
        )


@dataclass
class ExtractionPipeline:
    """提取管道，异步从对话轮次提取结构化记忆。"""

    llm_client: LLMClient
    store: MemoryStoreFacade
    conflict_resolver: Optional[ConflictResolverProtocol] = None
    extract_every_n: int = 1
    turn_counter: Dict[str, int] = field(default_factory=dict)

    EXTRACTION_SYSTEM_PROMPT = (
        "你是一个记忆提取助手。根据给定的对话片段，提取结构化的记忆项。\n\n"
        "每个记忆项必须包含：\n"
        '- category: "fact" | "preference" | "behavior" | "correction"（可用中文“事实/偏好/行为/纠正”）\n'
        "- content: 简洁的自然语言陈述（一句话）\n"
        '- confidence: "high" | "medium" | "low"\n'
        "- source_turn_id: 从哪个对话轮次提取的\n"
        "- entities: 提到的实体列表\n\n"
        "规则：\n"
        "1. 只提取明确陈述或强烈暗示的内容。\n"
        "2. 偏好必须捕捉倾向（喜欢/不喜欢），可选强度。\n"
        "3. 如果用户更正了之前的陈述，输出一个 \"correction\" 项。\n"
        "4. 不要从问候语或闲聊中臆想偏好。\n"
        "输出格式：JSON 数组。"
    )

    async def on_turn_complete(
        self,
        session_id: str,
        user_id: str,
        turns: List[Dict[str, Any]],
    ) -> None:
        """每轮对话完成后调用，达到阈值时触发异步提取。"""

        count = self.turn_counter.get(session_id, 0) + 1
        self.turn_counter[session_id] = count
        if count % self.extract_every_n == 0:
            asyncio.create_task(self._run_extraction(session_id, user_id, turns))

    async def on_session_end(
        self,
        session_id: str,
        user_id: str,
        all_turns: List[Dict[str, Any]],
    ) -> None:
        """会话结束时触发异步提取。"""

        asyncio.create_task(self._run_extraction(session_id, user_id, all_turns))

    async def _run_extraction(
        self,
        session_id: str,
        user_id: str,
        turns: List[Dict[str, Any]],
    ) -> None:
        extracted = await self._extract_from_turns(turns)
        if not extracted:
            logger.info(f"Extraction: {session_id}, {user_id} is empty")
            return
        for item in extracted:
            memory_item = item.to_memory_item(user_id=user_id, session_id=session_id)
            logger.info(f"Extraction: {session_id}, {user_id}: {memory_item}, 开始检测冲突")
            if memory_item is None:
                continue
            if self.conflict_resolver:
                await self.conflict_resolver.resolve_and_store(memory_item)
            else:
                await self.store.add(memory_item)

    async def _extract_from_turns(self, turns: Iterable[Dict[str, Any]]) -> List[ExtractedMemory]:
        messages = [
            {"role": "system", "content": self.EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": _format_turns(turns)},
        ]
        response = await self.llm_client.chat(messages=messages, temperature=0.2)
        logger.info(f"Extraction turns: {str(turns[:200])}, response: {response.content}")
        if response.content is None:
            return []
        content = _clean_json_content(response.content)
        payload = _load_json_payload(content)
        if payload is None:
            payload = await self._repair_payload(content)
            if payload is None:
                return _fallback_from_text(content, turns)
        if isinstance(payload, dict):
            for key in ("memories", "items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    payload = value
                    break
        if not isinstance(payload, list):
            return _fallback_from_text(content, turns)
        results: List[ExtractedMemory] = []
        for item in payload:
            if isinstance(item, dict):
                item = _normalize_item(item)
                item = _fill_item_defaults(item, turns)
            try:
                results.append(ExtractedMemory.model_validate(item))
            except Exception as e:
                print(f"[Extraction Error] Validation failed for item {item}: {e}")
                continue
        if results:
            return results
        return _fallback_from_text(content, turns)

    async def _repair_payload(self, content: str) -> Any | None:
        prompt = "将以下内容转换为 JSON 数组，只输出 JSON 数组，不要任何解释。"
        response = await self.llm_client.chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            temperature=0.0,
        )
        if response.content is None:
            return None
        repaired = _clean_json_content(response.content)
        return _load_json_payload(repaired)


def _load_json_payload(content: str) -> Any | None:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        left = content.find("[")
        right = content.rfind("]")
        if left == -1 or right == -1 or right <= left:
            left = content.find("{")
            right = content.rfind("}")
            if left == -1 or right == -1 or right <= left:
                return None
            sliced = content[left : right + 1]
        else:
            sliced = content[left : right + 1]
        try:
            return json.loads(sliced)
        except json.JSONDecodeError:
            return None


def _clean_json_content(content: str) -> str:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    def pick(keys: List[str], default: Any = None) -> Any:
        for key in keys:
            if key in item:
                return item[key]
        return default

    return {
        "category": pick(["category", "类别", "类型"], item.get("category")),
        "content": pick(["content", "内容"], item.get("content")),
        "confidence": pick(["confidence", "置信度"], item.get("confidence")),
        "source_turn_id": pick(
            ["source_turn_id", "source_turn", "turn_id", "来源轮次", "来源轮次id"],
            item.get("source_turn_id"),
        ),
        "entities": pick(["entities", "实体", "实体列表"], item.get("entities", [])),
    }


def _format_turns(turns: Iterable[Dict[str, Any]]) -> str:
    lines = []
    for idx, turn in enumerate(turns, start=1):
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", "")).strip()
        turn_id = str(turn.get("turn_id") or turn.get("id") or idx)
        if content:
            lines.append(f"[{turn_id}] {role}: {content}")
    return "\n".join(lines) if lines else "无有效对话片段。"


def _map_confidence(value: str) -> float:
    mapping = {
        "high": 0.9,
        "medium": 0.6,
        "low": 0.3,
        "高": 0.9,
        "中": 0.6,
        "低": 0.3,
    }
    return mapping.get(value.lower(), 0.5)


def _contains_preference(text: str) -> bool:
    lowered = text.lower()
    keywords = (
        "喜欢",
        "偏好",
        "爱好",
        "不喜欢",
        "讨厌",
        "不爱",
        "钟爱",
        "喜爱",
        "love",
        "like",
        "prefer",
        "favorite",
        "favourite",
        "dislike",
        "hate",
    )
    return any(keyword in lowered or keyword in text for keyword in keywords)


def _normalize_preference_content(text: str) -> str:
    value = text.strip()
    for token in ("请记住：", "请记住:", "我的偏好是", "偏好是"):
        value = value.replace(token, "")
    value = value.replace("我喜欢", "喜欢").replace("我不喜欢", "不喜欢")
    return value.strip()


def _infer_source_turn_id(turns: Iterable[Dict[str, Any]]) -> str:
    last_turn_id = "1"
    for idx, turn in enumerate(turns, start=1):
        turn_id = str(turn.get("turn_id") or turn.get("id") or idx)
        last_turn_id = turn_id
        if str(turn.get("role", "user")) == "user":
            content = str(turn.get("content", "")).strip()
            if content and _contains_preference(content):
                return turn_id
    return last_turn_id


def _fill_item_defaults(item: Dict[str, Any], turns: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    payload = dict(item)
    content = str(payload.get("content") or "").strip()
    if not content:
        return payload
    if not payload.get("confidence"):
        payload["confidence"] = "medium"
    if payload.get("source_turn_id") is not None:
        payload["source_turn_id"] = str(payload["source_turn_id"])
    if not payload.get("source_turn_id"):
        payload["source_turn_id"] = _infer_source_turn_id(turns)
    if not payload.get("category"):
        payload["category"] = "preference" if _contains_preference(content) else "fact"
    if payload.get("entities") is None:
        payload["entities"] = []
    return payload


def _fallback_from_text(content: str, turns: Iterable[Dict[str, Any]]) -> List[ExtractedMemory]:
    text = _normalize_preference_content(content.strip())
    if text and _contains_preference(text):
        return [
            ExtractedMemory(
                category="preference",
                content=text,
                confidence="medium",
                source_turn_id=_infer_source_turn_id(turns),
                entities=[],
            )
        ]
    return []

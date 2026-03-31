from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..llm.provider import LLMClient


class ProgressiveSummarizer:
    """维护滚动摘要，每 N 轮更新。"""

    def __init__(self, llm_client: LLMClient, summarize_every_n: int = 5) -> None:
        """初始化摘要器。

        Args:
            llm_client: LLM 客户端。
            summarize_every_n: 触发摘要的轮次数。
        """
        if summarize_every_n <= 0:
            raise ValueError("summarize_every_n must be positive")
        self.llm = llm_client
        self.n = summarize_every_n
        self.running_summary: Optional[str] = None
        self.unsummarized: List[Dict[str, Any]] = []
        self.turn_count: int = 0

    async def add_turn(
        self,
        user_msg: Dict[str, Any],
        assistant_msg: Dict[str, Any],
        tool_msgs: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """添加新轮次，并在达到阈值时触发摘要。"""
        self.turn_count += 1
        # 按顺序缓存本轮消息，便于统一格式化摘要
        self.unsummarized.append(user_msg)
        if tool_msgs:
            self.unsummarized.extend(tool_msgs)
        self.unsummarized.append(assistant_msg)
        if self.turn_count % self.n == 0:
            await self._do_summarize()

    async def _do_summarize(self) -> None:
        content = self._format_messages(self.unsummarized)
        # 若已有滚动摘要，则与新轮次合并更新
        if self.running_summary:
            prompt = (
                f"现有摘要：\n{self.running_summary}\n\n新轮次：\n{content}\n\n"
                "生成合并后的更新摘要。保留：关键主题、用户偏好、决策、重要工具结果。简洁。"
            )
        else:
            prompt = f"摘要对话：\n{content}\n\n保留关键主题、偏好、决策、工具结果。简洁。"
        response = await self.llm.chat(messages=[{"role": "user", "content": prompt}])
        self.running_summary = response.content or ""
        self.unsummarized = []

    async def summarize(self, messages: List[Dict[str, Any]]) -> str:
        """一次性摘要一批消息。"""
        content = self._format_messages(messages)
        prompt = f"将以下对话精炼为简洁摘要，保留关键信息：\n{content}"
        response = await self.llm.chat(messages=[{"role": "user", "content": prompt}])
        return response.content or ""

    def get_context(self, recent_turns: int = 3) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """获取当前摘要与最近未摘要消息。"""
        keep = max(recent_turns, 0) * 3
        if keep == 0:
            return self.running_summary, []
        # 每轮按 user/tool/assistant 三段计数
        return self.running_summary, self.unsummarized[-keep:]

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for message in messages:
            role = message.get("role", "unknown")
            content = self._content_to_text(message.get("content"))
            # 限制单条长度，避免提示词过长
            lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines)

    def _content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return str(content)

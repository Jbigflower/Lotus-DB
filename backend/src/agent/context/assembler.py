from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from config.logging import get_logic_logger
from ..config import AgentConfig
from ..memory.models import MemoryItem
from ..memory.runtime import MemoryRuntime
from ..types import AgentRole, ConversationHistory, RequestContext
from .summarizer import ProgressiveSummarizer


@dataclass(frozen=True)
class ContextBudget:
    """上下文预算定义。"""

    model_context_window: int = 128_000
    working_space_reserve: int = 4_000
    system_core: Tuple[int, int] = (1500, 2500)
    memory_context: Tuple[int, int] = (1500, 6000)
    conversation: Tuple[int, int] = (3000, 10000)
    tool_results: Tuple[int, int] = (1000, 4000)


CONTEXT_PRESETS: Dict[str, ContextBudget] = {
    "main_agent": ContextBudget(
        model_context_window=128_000,
        working_space_reserve=4_000,
        system_core=(1500, 2500),
        memory_context=(1500, 6000),
        conversation=(3000, 10000),
        tool_results=(1000, 4000),
    ),
    "delegated_sub_agent": ContextBudget(
        model_context_window=32_000,
        working_space_reserve=2_000,
        system_core=(500, 1000),
        memory_context=(500, 2000),
        conversation=(0, 0),
        tool_results=(1000, 3000),
    ),
}


class ContextBuilder:
    """
    上下文构建入口，负责消息组装与预算治理。

    设计目标：
    - 将“消息构建”与“预算治理”收口为单一职责入口
    - 统一 system/memory/history/user 的拼装规则
    - 让 Loop 仅负责调度与执行，降低耦合
    """

    def __init__(
        self,
        config: AgentConfig,
        assembler: ContextAssembler,
        memory_runtime: Optional[MemoryRuntime] = None,
    ) -> None:
        """初始化上下文构建器。

        Args:
            config: Agent 配置，包含角色、目标、约束、工具与记忆权限等。
            assembler: 预算治理组件，负责压缩/裁剪与顺序修复。
            memory_runtime: 记忆运行时，用于按需加载与召回。
        """
        self._config = config
        self._assembler = assembler
        self._memory_runtime = memory_runtime
        self._logger = get_logic_logger("agent.context.builder")

    async def build_messages(
        self,
        user_input: str,
        history: Optional[ConversationHistory],
        ctx: RequestContext,
    ) -> List[Dict[str, Any]]:
        """构建当前轮次的上下文消息列表。

        组装顺序：
        1) system_core（系统提示与系统级记忆）
        2) initial_context（配置中预置上下文）
        3) memory_context（用户画像/相关记忆/会话记忆）
        4) 历史消息
        5) 当前 user 输入

        约束说明：
        - 记忆注入仅在启用记忆权限且运行时可用时发生
        - 若历史中已存在系统/用户摘要，避免重复注入
        """
        system_core: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": self._build_system_prompt(),
                "section": "system_core",
            }
        ]

        history_messages = self._history_messages(history)
        memory_context: List[Dict[str, Any]] = []
        if self._memory_runtime and self._has_memory_access():
            has_agent_core = self._has_memory_block(history_messages, "系统规则摘要")
            has_user_profile = self._has_memory_block(history_messages, "用户画像摘要")

            if not has_agent_core:
                agent_core = await self._load_agent_core()
                if agent_core:
                    system_core.append(
                        {
                            "role": "system",
                            "content": self._format_memory_block("系统规则摘要", agent_core),
                            "section": "system_core",
                        }
                    )

            if not has_user_profile:
                user_profile = await self._load_user_profile(ctx.user_id)
                if user_profile:
                    memory_context.append(
                        {
                            "role": "system",
                            "content": self._format_memory_block("用户画像摘要", user_profile),
                            "section": "memory_context",
                        }
                    )

            assembled = await self._retrieve_on_demand(user_input, ctx)
            if assembled:
                memory_context.append(
                    {
                        "role": "system",
                        "content": assembled,
                        "section": "memory_context",
                    }
                )

        messages: List[Dict[str, Any]] = []
        messages.extend(system_core)
        messages.extend(self._config.initial_context)
        messages.extend(memory_context)
        if history_messages:
            messages.extend(history_messages)
        messages.append({"role": "user", "content": user_input})
        return messages

    async def prepare_for_llm(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对消息进行预算治理，保证符合模型上下文限制。"""
        return await self._assembler.fit_to_budget(messages, self._config)

    def _has_memory_access(self) -> bool:
        """判断当前配置是否启用记忆层访问。"""
        access = self._config.memory_access
        return any(access.get(key, False) for key in ("agent_memory", "user_memory", "session_memory"))

    async def _load_agent_core(self) -> List[MemoryItem]:
        """加载 Agent 侧核心规则/策略记忆。"""
        if not self._memory_runtime or not self._config.memory_access.get("agent_memory", False):
            return []
        return await self._memory_runtime.get_agent_core_memories(limit=10)

    async def _load_user_profile(self, user_id: str) -> List[MemoryItem]:
        """加载用户画像摘要记忆。"""
        if not self._memory_runtime or not self._config.memory_access.get("user_memory", False):
            return []
        return await self._memory_runtime.get_user_profile_memories(user_id=user_id, limit=10)

    async def _retrieve_on_demand(self, user_input: str, ctx: RequestContext) -> Optional[str]:
        """按需召回记忆并拼装为可注入文本块。"""
        if not self._memory_runtime:
            return None
        access = self._config.memory_access
        if not any(access.get(key, False) for key in ("agent_memory", "user_memory", "session_memory")):
            return None
        retriever = await self._memory_runtime.get_retriever()
        assembled = await retriever.retrieve_for_context(
            query=user_input,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
        )
        agent_items = assembled.agent if access.get("agent_memory", False) else []
        user_items = assembled.user if access.get("user_memory", False) else []
        session_items = assembled.session if access.get("session_memory", False) else []
        blocks = []
        if agent_items:
            blocks.append(self._format_memory_block("相关知识", agent_items))
        if user_items:
            blocks.append(self._format_memory_block("相关用户记忆", user_items))
        if session_items:
            blocks.append(self._format_memory_block("会话记忆", session_items))
        content = "\n\n".join(blocks).strip()
        return content or None

    @staticmethod
    def _history_messages(history: Optional[ConversationHistory | List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """兼容 ConversationHistory 与原始消息列表的转换逻辑。"""
        if history is None:
            return []
        if hasattr(history, "to_llm_messages"):
            return history.to_llm_messages()
        if isinstance(history, list):
            return history
        return []

    @staticmethod
    def _format_memory_block(title: str, items: List[MemoryItem]) -> str:
        """将记忆列表格式化为系统消息可用的文本块。"""
        lines = [item.content.strip() for item in items if item.content]
        body = "\n".join(f"- {line}" for line in lines)
        return f"{title}\n{body}".strip()

    @staticmethod
    def _has_memory_block(messages: List[Dict[str, Any]], title: str) -> bool:
        """检测历史中是否已存在指定标题的记忆块。"""
        prefix = title.strip()
        for msg in messages:
            if msg.get("role") != "system":
                continue
            content = (msg.get("content") or "").strip()
            if content.startswith(prefix):
                return True
        return False

    def _build_system_prompt(self) -> str:
        """构建系统提示词，包含角色、目标、约束与可用工具。"""
        parts = [
            f"角色: {self._config.role_description}",
            f"目标: {self._config.goal}",
        ]
        if self._config.constraints:
            parts.append("约束: " + "；".join(self._config.constraints))
        if self._config.allowed_tools:
            parts.append("可用工具: " + "，".join(self._config.allowed_tools))
        return "\n".join(parts)


class ContextAssembler:
    """基于预算的上下文组装器。"""

    def __init__(
        self,
        token_counter: Callable[[str], int],
        summarizer: ProgressiveSummarizer,
    ) -> None:
        """初始化上下文组装器。

        Args:
            token_counter: 字符串 -> token 数量的计数函数。
            summarizer: 渐进式摘要器。
        """
        self._count = token_counter
        self._summarizer = summarizer
        self._logger = get_logic_logger("agent.context.assembler")

    def assemble(
        self,
        system_core: List[Dict[str, Any]],
        memory_context: List[Dict[str, Any]],
        conversation: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        # 记录简单组装操作
        self._logger.debug(f"执行简单组装 - 系统核心: {len(system_core)}, 记忆: {len(memory_context)}, 对话: {len(conversation)}, 工具: {len(tool_results)}")
        
        return [
            *system_core,
            *memory_context,
            *conversation,
            *tool_results,
        ]

    async def fit_to_budget(
        self,
        messages: List[Dict[str, Any]],
        config: AgentConfig,
    ) -> List[Dict[str, Any]]:
        """确保消息列表符合上下文预算。"""
        budget = self._get_budget(config)
        total_limit = budget.model_context_window - budget.working_space_reserve
        
        # 记录上下文管理开始
        self._logger.info(f"开始上下文管理，角色: {config.role}, 预算窗口: {budget.model_context_window}, 工作空间保留: {budget.working_space_reserve}")
        
        # 将消息按分区归类，分别进行压缩与裁剪
        system_core, memory_context, conversation, tool_results = self._partition_messages(messages)
        
        # 记录分区统计
        self._logger.debug(f"消息分区统计 - 系统核心: {len(system_core)}, 记忆上下文: {len(memory_context)}, 对话: {len(conversation)}, 工具结果: {len(tool_results)}")
        conversation, conversation_summary = await self._compress_conversation(
            conversation,
            budget.conversation[1],
        )
        memory_context, memory_summary = await self._compress_section(
            memory_context,
            budget.memory_context[1],
            keep_recent_count=3,
            summary_label="记忆摘要",
        )
        tool_results, tool_summary = await self._compress_section(
            tool_results,
            budget.tool_results[1],
            keep_recent_count=3,
            summary_label="工具摘要",
        )

        # 记录压缩结果
        if conversation_summary:
            self._logger.debug("对话部分已压缩，生成对话摘要")
        if memory_summary:
            self._logger.debug("记忆上下文已压缩，生成记忆摘要")
        if tool_summary:
            self._logger.debug("工具结果已压缩，生成工具摘要")

        summaries = [summary for summary in [conversation_summary, memory_summary, tool_summary] if summary]
        if summaries:
            system_core.extend(summaries)
            self._logger.debug(f"添加了 {len(summaries)} 个摘要到系统核心")
        
        # system_core 保留最新的关键系统信息
        system_core = self._trim_section(system_core, budget.system_core[1], keep_recent=True)
        self._logger.debug(f"系统核心裁剪后: {len(system_core)} 条消息")

        assembled = self._assemble_preserving_order(
            messages,
            system_core,
            memory_context,
            conversation,
            tool_results,
        )
        assembled = self._ensure_tool_call_pairs(assembled)
        
        total_tokens = self._total_tokens(assembled)
        self._logger.debug(f"组装后总token数: {total_tokens}, 预算限制: {total_limit}")
        
        if total_tokens <= total_limit:
            self._logger.info(f"上下文管理完成，总token数: {total_tokens}, 符合预算要求")
            return assembled

        self._logger.warning(f"上下文超出预算，开始裁剪。当前: {total_tokens}, 限制: {total_limit}")
        
        return self._trim_to_total_limit(
            messages,
            system_core,
            memory_context,
            conversation,
            tool_results,
            total_limit,
        )

    def _get_budget(self, config: AgentConfig) -> ContextBudget:
        preset_key = "main_agent" if config.role == AgentRole.MAIN else "delegated_sub_agent"
        return CONTEXT_PRESETS[preset_key]

    def _partition_messages(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        system_core: List[Dict[str, Any]] = []
        memory_context: List[Dict[str, Any]] = []
        conversation: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []

        for message in messages:
            section = message.get("section")
            if section == "system_core":
                system_core.append(message)
                continue
            if section == "memory_context":
                memory_context.append(message)
                continue
            if section == "conversation":
                conversation.append(message)
                continue
            if section == "tool_results":
                tool_results.append(message)
                continue

            role = message.get("role")
            if role == "system":
                system_core.append(message)
            elif role == "tool":
                tool_results.append(message)
            else:
                conversation.append(message)

        # 记录分区结果
        self._logger.debug(f"消息分区完成 - 按section分类: 系统核心({len(system_core)}), 记忆({len(memory_context)}), 对话({len(conversation)}), 工具({len(tool_results)})")
        
        return system_core, memory_context, conversation, tool_results

    def _trim_section(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        keep_recent: bool,
    ) -> List[Dict[str, Any]]:
        if max_tokens <= 0:
            return []
        # 根据是否保留最近消息决定遍历方向
        iterable: Iterable[Dict[str, Any]] = reversed(messages) if keep_recent else messages
        selected: List[Dict[str, Any]] = []
        total = 0
        for message in iterable:
            tokens = self._count_message_tokens(message)
            if total + tokens > max_tokens and selected:
                break
            selected.append(message)
            total += tokens
        if keep_recent:
            selected.reverse()
        return selected

    async def _compress_conversation(
        self,
        conversation: List[Dict[str, Any]],
        max_tokens: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        total_tokens = self._section_tokens(conversation)
        if total_tokens <= max_tokens:
            return conversation, None
        
        # 记录对话压缩开始
        self._logger.debug(f"对话压缩开始，当前token数: {total_tokens}, 最大限制: {max_tokens}")
        
        # 保留最近 6 条，较早部分生成摘要
        recent = conversation[-6:]
        older = conversation[:-6]
        if not older:
            return conversation, None
        
        self._logger.debug(f"对话压缩 - 保留最近 {len(recent)} 条，摘要 {len(older)} 条")
        
        summary_text = await self._summarizer.summarize(older)
        summary_message = {
            "role": "system",
            "content": f"[对话摘要] {summary_text}",
            "section": "system_core",
        }
        
        self._logger.debug(f"对话摘要生成完成，摘要长度: {len(summary_text)} 字符")
        
        return recent, summary_message

    async def _compress_section(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        keep_recent_count: int,
        summary_label: str,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if max_tokens <= 0:
            return [], None
        total_tokens = self._section_tokens(messages)
        if total_tokens <= max_tokens:
            return messages, None
        
        # 记录分区压缩开始
        self._logger.debug(f"{summary_label}压缩开始，当前token数: {total_tokens}, 最大限制: {max_tokens}")
        
        # 保留最近几条，老消息尝试摘要
        keep_recent = messages[-keep_recent_count:] if keep_recent_count > 0 else []
        older = messages[:-keep_recent_count] if keep_recent_count > 0 else messages
        
        self._logger.debug(f"{summary_label}压缩 - 保留最近 {len(keep_recent)} 条，摘要 {len(older)} 条")
        
        summary_message = None
        if older:
            summary_text = await self._summarizer.summarize(older)
            summary_message = {
                "role": "system",
                "content": f"[{summary_label}] {summary_text}",
                "section": "system_core",
            }
            self._logger.debug(f"{summary_label}摘要生成完成，摘要长度: {len(summary_text)} 字符")
        
        trimmed_recent = self._trim_section(keep_recent, max_tokens, keep_recent=True)
        
        if len(trimmed_recent) < len(keep_recent):
            self._logger.debug(f"{summary_label}最近消息进一步裁剪: {len(keep_recent)} -> {len(trimmed_recent)} 条")
        
        return trimmed_recent, summary_message

    def _trim_to_total_limit(
        self,
        original_messages: List[Dict[str, Any]],
        system_core: List[Dict[str, Any]],
        memory_context: List[Dict[str, Any]],
        conversation: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]],
        total_limit: int,
    ) -> List[Dict[str, Any]]:
        system_core = list(system_core)
        memory_context = list(memory_context)
        conversation = list(conversation)
        tool_results = list(tool_results)

        iteration = 0
        max_iterations = 50  # 防止无限循环
        
        while iteration < max_iterations:
            iteration += 1
            assembled = self._assemble_preserving_order(
                original_messages,
                system_core,
                memory_context,
                conversation,
                tool_results,
            )
            assembled = self._ensure_tool_call_pairs(assembled)
            total_tokens = self._total_tokens(assembled)
            if total_tokens <= total_limit:
                self._logger.info(f"裁剪完成，最终token数: {total_tokens}, 迭代次数: {iteration}")
                return assembled

            # 按优先级淘汰：旧对话 -> 工具结果 -> 记忆 -> 系统
            if len(conversation) > 6:
                removed = conversation.pop(0)
                self._logger.debug(f"移除旧对话消息，剩余对话: {len(conversation)}")
            elif tool_results:
                removed = tool_results.pop(0)
                self._logger.debug(f"移除工具结果消息，剩余工具结果: {len(tool_results)}")
            elif memory_context:
                removed = memory_context.pop(0)
                self._logger.debug(f"移除记忆上下文消息，剩余记忆: {len(memory_context)}")
            elif len(system_core) > 1:
                removed = system_core.pop()
                self._logger.debug(f"移除系统核心消息，剩余系统核心: {len(system_core)}")
            else:
                self._logger.warning("无法进一步裁剪，已达到最小消息数量")
                break
            total_tokens -= self._count_message_tokens(removed)

        self._logger.warning(f"裁剪完成但可能仍超出预算，最终token数: {total_tokens}")
        return assembled

    def _assemble_preserving_order(
        self,
        original_messages: List[Dict[str, Any]],
        system_core: List[Dict[str, Any]],
        memory_context: List[Dict[str, Any]],
        conversation: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        original_ids = {id(msg) for msg in original_messages}
        selected = [
            msg
            for msg in (system_core + memory_context + conversation + tool_results)
            if id(msg) in original_ids
        ]
        selected_ids = {id(msg) for msg in selected}
        base_order = [msg for msg in original_messages if id(msg) in selected_ids]
        summaries = [msg for msg in system_core if id(msg) not in original_ids]
        if not summaries:
            return base_order
        for idx, msg in enumerate(base_order):
            if msg.get("role") == "system" and msg.get("section") != "memory_context":
                return base_order[: idx + 1] + summaries + base_order[idx + 1 :]
        return summaries + base_order

    def _ensure_tool_call_pairs(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []
        expected_ids: Optional[set[str]] = None

        def _strip_tool_calls(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            cleaned = dict(message)
            cleaned.pop("tool_calls", None)
            if cleaned.get("content") is None:
                return None
            return cleaned

        for msg in messages:
            role = msg.get("role")
            if expected_ids:
                if role == "tool":
                    tool_id = msg.get("tool_call_id")
                    if tool_id in expected_ids:
                        pending.append(msg)
                        expected_ids.discard(tool_id)
                        if not expected_ids:
                            output.extend(pending)
                            pending = []
                            expected_ids = None
                    continue
                if pending:
                    cleaned = _strip_tool_calls(pending[0])
                    if cleaned:
                        output.append(cleaned)
                pending = []
                expected_ids = None
                if role != "tool":
                    output.append(msg)
                continue

            if role == "assistant" and msg.get("tool_calls"):
                tool_calls = msg.get("tool_calls") or []
                ids = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id")
                        if tc_id:
                            ids.append(tc_id)
                if ids:
                    pending = [msg]
                    expected_ids = set(ids)
                    continue
            if role == "tool":
                continue
            output.append(msg)

        if expected_ids and pending:
            cleaned = _strip_tool_calls(pending[0])
            if cleaned:
                output.append(cleaned)

        return output

    def _total_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return sum(self._count_message_tokens(message) for message in messages)

    def _section_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return sum(self._count_message_tokens(message) for message in messages)

    def _count_message_tokens(self, message: Dict[str, Any]) -> int:
        content = message.get("content")
        if content is None:
            return 0
        if isinstance(content, str):
            return self._count(content)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(item, str):
                    parts.append(item)
            return self._count("\n".join(parts))
        return self._count(str(content))

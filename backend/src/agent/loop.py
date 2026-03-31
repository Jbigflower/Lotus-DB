from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from config.logging import get_logic_logger
from .config import AgentConfig
from .context.assembler import ContextAssembler, ContextBuilder
from .context.summarizer import ProgressiveSummarizer
from .delegation import DelegationHandler
from .llm.provider import LLMClient, LLMResponse
from .memory.runtime import MemoryRuntime
from .tools.registry import ToolRegistry
from .types import ConversationHistory, RequestContext, StreamEvent, ToolResult


class AgentLoop:
    """
    智能体核心循环。

    职责：
    - 构造 LLM 消息
    - 调用 LLM（含重试策略）
    - 执行工具调用
    - 检测工具循环
    - 产出 StreamEvent 事件流
    """

    # ── 可配置常量 ─────────────────────────────────────
    TOOL_RESULT_MAX_CHARS = 16_000
    TOOL_LOOP_THRESHOLD = 3
    MAX_RETRY_TIMEOUT = 2
    MAX_RETRY_RATE_LIMIT = 2
    MAX_RETRY_OVERFLOW = 1
    INITIAL_BACKOFF = 2

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        config: AgentConfig,
        context_builder: Optional[ContextBuilder] = None,
        context_assembler: Optional[ContextAssembler] = None,
        delegation_handler: Optional[DelegationHandler] = None,
        memory_runtime: Optional[MemoryRuntime] = None,
    ) -> None:
        self.logger = get_logic_logger("agent_loop")
        self.llm = llm
        self.tools = tools
        self.config = config
        self.memory_runtime = memory_runtime
        if context_builder:
            self.context_builder = context_builder
        else:
            assembler = context_assembler or ContextAssembler(
                token_counter=self._token_counter,
                summarizer=ProgressiveSummarizer(llm_client=llm),
            )
            self.context_builder = ContextBuilder(
                config=self.config,
                assembler=assembler,
                memory_runtime=memory_runtime,
            )
        self.delegation_handler = delegation_handler or DelegationHandler(
            tool_registry=tools,
            llm_client=llm,
            memory_runtime=memory_runtime,
        )

    # ── 主循环 ────────────────────────────────────────

    async def run(
        self,
        user_input: str,
        ctx: RequestContext,
        history: Optional[ConversationHistory] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        运行智能体循环。

        产出事件类型：
        - tool_start / tool_end: 工具调用生命周期
        - text_delta: 文本内容（当前为完整回复，后续支持真流式）
        - error: 错误信息
        - done: 循环结束
        """
        messages = await self.context_builder.build_messages(user_input, history, ctx)
        tool_loop_tracker = _ToolLoopTracker(threshold=self.TOOL_LOOP_THRESHOLD)

        self.logger.info(
            "agent_loop_start",
            extra={"trace_id": ctx.trace_id, "user_id": ctx.user_id},
        )

        try:
            async for event in self._loop(messages, ctx, tool_loop_tracker):
                yield event
        except Exception as exc:
            self.logger.exception(
                "agent_loop_unhandled_error",
                extra={"trace_id": ctx.trace_id},
            )
            error_msg = f"内部错误: {str(exc)[:200]}"
            yield {"type": "error", "data": {"error_type": "internal_error", "message": error_msg}}
            yield {"type": "done", "data": {"content": error_msg}}

    async def _loop(
        self,
        messages: List[Dict[str, Any]],
        ctx: RequestContext,
        tracker: _ToolLoopTracker,
    ) -> AsyncGenerator[StreamEvent, None]:
        for iteration in range(1, self.config.max_iterations + 1):
            self.logger.debug(
                "agent_loop_iteration",
                extra={"iteration": iteration, "trace_id": ctx.trace_id},
            )

            streamed_text = False
            if self.llm.supports_stream():
                messages = await self.context_builder.prepare_for_llm(messages)
                event_stream, response_future = self.llm.stream_response(
                    messages=messages,
                    tools=self._get_tool_schemas(),
                    model=None,
                )
                async for event in event_stream:
                    if event["type"] == "text_delta":
                        streamed_text = True
                    yield event
                response = await response_future
                error_type = None
                if response.finish_reason == "error":
                    error_type = self._classify_error(response.content)
            else:
                response, error_type, messages = await self._call_llm_with_retry(messages)

            if error_type:
                self.logger.warning(
                    "agent_loop_llm_error",
                    extra={"error_type": error_type, "trace_id": ctx.trace_id},
                )
                yield {"type": "error", "data": {"error_type": error_type, "message": response.content or ""}}
                yield {"type": "done", "data": {"content": response.content or ""}}
                return

            # ── 工具调用分支 ──
            if response.has_tool_calls:
                should_continue = True
                async for event in self._handle_tool_calls(
                    response, messages, ctx, tracker
                ):
                    yield event
                    # 如果工具执行中遇到致命错误，上层可决定是否中断
                continue

            # ── 文本回复分支 ──
            content = response.content or ""
            self.logger.info(
                "agent_loop_done",
                extra={"iteration": iteration, "content_len": len(content), "trace_id": ctx.trace_id},
            )
            if content and not streamed_text:
                yield {"type": "text_delta", "data": {"content": content}}
            yield {"type": "done", "data": {"content": content}}
            return

        # ── 超出最大迭代 ──
        fallback = (
            f"已达到最大迭代次数（{self.config.max_iterations}），"
            "仍未完成任务。请将问题拆分为更小步骤。"
        )
        self.logger.warning("agent_loop_max_iterations", extra={"trace_id": ctx.trace_id})
        yield {"type": "text_delta", "data": {"content": fallback}}
        yield {"type": "done", "data": {"content": fallback}}

    # ── 工具调用处理 ──────────────────────────────────

    async def _handle_tool_calls(
        self,
        response: LLMResponse,
        messages: List[Dict[str, Any]],
        ctx: RequestContext,
        tracker: _ToolLoopTracker,
    ) -> AsyncGenerator[StreamEvent, None]:
        """处理一轮 LLM 返回的所有 tool_calls。"""
        # 先追加 assistant 消息（含 tool_calls）
        messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": [tc.to_openai_tool_call() for tc in response.tool_calls],
        })

        tool_calls = list(response.tool_calls)
        tasks: List[asyncio.Task[ToolResult]] = []

        for tool_call in tool_calls:
            tool_name = tool_call.name

            # ── 循环检测 ──
            if tracker.record_and_check(tool_name):
                self.logger.warning(
                    f"tool_loop_detected, System Message: 检测到工具 {tool_name} 被重复调用，可能陷入循环。"
                        "请反思当前策略，尝试直接回答或更换工具。",
                    extra={"tool_name": tool_name, "trace_id": ctx.trace_id},
                )
                messages.append({
                    "role": "system",
                    "content": (
                        f"检测到工具 '{tool_name}' 被重复调用，可能陷入循环。"
                        "请反思当前策略，尝试直接回答或更换工具。"
                    ),
                })
                tracker.reset()

            # ── 执行工具 ──
            yield {
                "type": "tool_start",
                "data": {"tool_call_id": tool_call.id, "name": tool_name, "args": tool_call.arguments},
            }

            tasks.append(asyncio.create_task(self._execute_tool(tool_name, tool_call.arguments, ctx)))

        results = await asyncio.gather(*tasks)

        for tool_call, tool_result in zip(tool_calls, results):
            tool_name = tool_call.name
            if tool_result.is_error:
                self.logger.warning(
                    f"tool_execution_error, tool_name={tool_name}, error={tool_result.error}, error_reason={tool_result.output} args={tool_call.arguments}",
                    extra={"tool_name": tool_name, "error": tool_result.error, "trace_id": ctx.trace_id},
                )
                yield {"type": "error", "data": {"error_type": "tool_exception", "message": tool_result}}

            yield {
                "type": "tool_end",
                "data": {"tool_call_id": tool_call.id, "name": tool_name, "result": tool_result.output},
            }

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": tool_result.output,
            })

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取当前智能体可用的所有工具 Schema（包含动态注入的 delegate 工具）。"""
        schemas = self.tools.get_tool_schemas(self.config.allowed_tools)
        if self.config.can_delegate:
            schemas.append({
                "type": "function",
                "function": {
                    "name": "delegate",
                    "description": "委派一个子智能体处理特定子任务。将复杂的、需要多步搜索、或者相对独立的子任务交由专长领域的子智能体执行。如果需要委派多个子任务（例如分别分析多个目标），请务必在同一个回合（一次回复）中并行发起多个 delegate 调用，以提高执行效率。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_description": {
                                "type": "string",
                                "description": "要委派的具体任务描述"
                            },
                            "context": {
                                "type": "string",
                                "description": "子智能体执行任务所需的相关上下文信息"
                            },
                            "expected_output": {
                                "type": "string",
                                "description": "期望子智能体返回的输出格式或具体内容"
                            },
                            "required_tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "指定子智能体可用的工具名称列表（不传则使用默认或特定领域的工具）"
                            },
                            "specialist_type": {
                                "type": "string",
                                "enum": ["general", "media_search", "asset_management", "external_research"],
                                "description": "子智能体的专家类型（general 为通用）"
                            }
                        },
                        "required": ["task_description", "context", "expected_output"]
                    }
                }
            })
        return schemas

    async def _execute_tool(
        self,
        name: str,
        args: Dict[str, Any],
        ctx: RequestContext,
    ) -> ToolResult:
        """执行单个工具。"""
        try:
            if name == "delegate":
                return await self._execute_delegation(args, ctx)

            raw_result = await self.tools.execute(name, args, ctx=ctx)
            if isinstance(raw_result, ToolResult):
                return ToolResult(
                    output=self._trim_result(raw_result.output),
                    error=raw_result.error,
                )
            output = self._trim_result(str(raw_result))
            return ToolResult(output=output)

        except Exception as exc:
            self.logger.exception(
                "tool_exception",
                extra={"tool_name": name, "trace_id": ctx.trace_id},
            )
            error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
            return ToolResult(
                output=f"工具 '{name}' 执行失败: {error_msg}",
                error=error_msg,
            )

    async def _execute_delegation(
        self, args: Dict[str, Any], ctx: RequestContext
    ) -> ToolResult:
        """执行委托调用。"""
        if not self.config.can_delegate:
            return ToolResult(output="Error: 当前 Agent 不允许委托", error="delegate_not_allowed")

        required_tools = args.get("required_tools") or []
        if not isinstance(required_tools, list):
            required_tools = []

        result = await self.delegation_handler.handle(
            task_description=str(args.get("task_description", "")),
            context=str(args.get("context", "")),
            expected_output=str(args.get("expected_output", "")),
            required_tools=required_tools,
            specialist_type=str(args.get("specialist_type", "general")),
            ctx=ctx,
        )
        return ToolResult(output=self._trim_result(result))

    # ── LLM 调用与重试 ───────────────────────────────

    async def _call_llm_with_retry(
        self,
        messages: List[Dict[str, Any]],
    ) -> Tuple[LLMResponse, Optional[str], List[Dict[str, Any]]]:
        """
        调用 LLM，含分类重试策略。

        重试策略:
        - timeout: 重试 2 次，固定延迟
        - rate_limit: 重试 2 次，指数退避
        - token_overflow: 重试 1 次，先压缩上下文
        - 其他错误: 不重试，直接返回
        """
        retry_budget = {
            "llm_timeout": self.MAX_RETRY_TIMEOUT,
            "llm_rate_limit": self.MAX_RETRY_RATE_LIMIT,
            "token_overflow": self.MAX_RETRY_OVERFLOW,
        }
        backoff = self.INITIAL_BACKOFF
        max_total_attempts = sum(retry_budget.values()) + 1  # 兜底防死循环

        for attempt in range(max_total_attempts):
            messages = await self.context_builder.prepare_for_llm(messages)

            response = await self.llm.chat(
                messages=messages,
                tools=self._get_tool_schemas(),
                model=None,
            )

            if response.finish_reason != "error":
                return response, None, messages

            error_type = self._classify_error(response.content)

            # 无法分类的错误，直接返回
            if error_type is None or error_type not in retry_budget:
                return response, error_type or "llm_error", messages

            # 重试次数耗尽
            if retry_budget[error_type] <= 0:
                return response, error_type, messages

            retry_budget[error_type] -= 1

            self.logger.warning(
                "llm_retry",
                extra={
                    "error_type": error_type,
                    "remaining": retry_budget[error_type],
                    "attempt": attempt + 1,
                },
            )

            if error_type == "llm_timeout":
                await asyncio.sleep(2 * (self.MAX_RETRY_TIMEOUT - retry_budget[error_type]))

            elif error_type == "llm_rate_limit":
                retry_after = self._parse_retry_after(response.content)
                delay = retry_after if retry_after is not None else backoff
                backoff = min(backoff * 2, 60)  # 最大 60 秒
                await asyncio.sleep(delay)

            elif error_type == "token_overflow":
                messages = self._truncate_messages_safe(messages)

        # 理论上不会走到这里，但作为兜底
        return response, "llm_error_exhausted", messages

    # ── 消息截断（安全版本）─────────────────────────────

    def _truncate_messages_safe(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        安全截断消息：
        1. 保留 system prompt（第一条）
        2. 保留最后一条 user 消息
        3. 保留最近的 tool_call/tool 配对
        4. 中间部分按轮次移除最旧的
        """
        if len(messages) <= 4:
            return messages

        system = [messages[0]] if messages[0].get("role") == "system" else []
        rest = messages[len(system):]

        # 找到最后一条 user 消息的位置
        last_user_idx = None
        for i in range(len(rest) - 1, -1, -1):
            if rest[i].get("role") == "user":
                last_user_idx = i
                break

        if last_user_idx is None:
            # 没有 user 消息，保留最后几条
            return system + rest[-3:]

        # 保留 last_user 及之后的所有消息（包括后续的 tool 交互）
        tail = rest[last_user_idx:]

        # 如果 tail 本身就很长，说明是工具交互太多，保留 system + tail
        if len(system) + len(tail) >= len(messages) - 2:
            # 只能粗暴截断 tail
            return system + tail[-6:]

        return system + tail

    # ── 工具函数 ──────────────────────────────────────

    def _trim_result(self, result: str) -> str:
        if len(result) <= self.TOOL_RESULT_MAX_CHARS:
            return result
        return result[: self.TOOL_RESULT_MAX_CHARS] + "\n...(结果已截断)"

    @staticmethod
    def _classify_error(content: Optional[str]) -> Optional[str]:
        if not content:
            return None
        lowered = content.lower()
        if "timeout" in lowered or "timed out" in lowered:
            return "llm_timeout"
        if "rate limit" in lowered or "429" in lowered:
            return "llm_rate_limit"
        if any(kw in lowered for kw in ("context length", "maximum context", "too many tokens")):
            return "token_overflow"
        return None

    @staticmethod
    def _parse_retry_after(content: Optional[str]) -> Optional[int]:
        if not content:
            return None
        match = re.search(r"retry[-_\s]?after[:\s]+(\d+)", content.lower())
        if not match:
            return None
        try:
            val = int(match.group(1))
            return min(val, 120)  # 上限 120 秒
        except ValueError:
            return None

    @staticmethod
    def _token_counter(text: str) -> int:
        """粗略 token 计数。中文按字符计，英文按空格分词。"""
        if not text:
            return 0
        # 简单策略：中文字符约 1 token，英文约 4 字符 1 token
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        non_chinese = len(text) - chinese_chars
        return chinese_chars + max(1, non_chinese // 4)


class _ToolLoopTracker:
    """
    工具循环检测器。

    支持检测：
    - 连续同名调用: A → A → A
    - 交替循环: A → B → A → B（通过滑动窗口）
    """

    def __init__(self, threshold: int = 3, window_size: int = 8) -> None:
        self._threshold = threshold
        self._window_size = window_size
        self._history: List[str] = []

    def record_and_check(self, tool_name: str) -> bool:
        """记录调用并返回是否检测到循环。"""
        self._history.append(tool_name)
        if len(self._history) > self._window_size:
            self._history = self._history[-self._window_size:]

        # 检测 1: 连续同名调用
        consecutive = 0
        for name in reversed(self._history):
            if name == tool_name:
                consecutive += 1
            else:
                break
        if consecutive >= self._threshold:
            return True

        # 检测 2: 周期性循环（如 A→B→A→B）
        if len(self._history) >= 4:
            for period in range(2, len(self._history) // 2 + 1):
                pattern = self._history[-period:]
                prev = self._history[-2 * period: -period]
                if pattern == prev:
                    return True

        return False

    def reset(self) -> None:
        self._history.clear()

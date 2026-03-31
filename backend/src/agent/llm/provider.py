from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import string
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Tuple

from ..types import StreamEvent


CompletionFn = Callable[..., Awaitable[Any]]
StreamFn = Callable[..., AsyncGenerator[Any, None]]

_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name", "reasoning_content"})
_ALNUM = string.ascii_letters + string.digits


def _short_tool_id() -> str:
    """生成 9 位字母数字工具调用 ID。"""
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


@dataclass
class ToolCallRequest:
    """LLM 返回的工具调用请求。"""

    id: str
    name: str
    arguments: Dict[str, Any]
    provider_specific_fields: Optional[Dict[str, Any]] = None
    function_provider_specific_fields: Optional[Dict[str, Any]] = None

    def to_openai_tool_call(self) -> Dict[str, Any]:
        """序列化为 OpenAI 工具调用格式。"""
        tool_call = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }
        if self.provider_specific_fields:
            tool_call["provider_specific_fields"] = self.provider_specific_fields
        if self.function_provider_specific_fields:
            tool_call["function"]["provider_specific_fields"] = self.function_provider_specific_fields
        return tool_call


@dataclass
class LLMResponse:
    """LLM 响应对象。"""

    content: Optional[str]
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    reasoning_content: Optional[str] = None
    thinking_blocks: Optional[List[Dict[str, Any]]] = None

    @property
    def has_tool_calls(self) -> bool:
        """判断是否包含工具调用。"""
        return len(self.tool_calls) > 0


@dataclass(frozen=True)
class GenerationSettings:
    """LLM 生成默认参数。"""

    temperature: float = 0.7
    max_tokens: int = 4096
    reasoning_effort: Optional[str] = None


class LLMClient:
    """LLM Provider 客户端，负责消息清洗、重试与响应解析。"""

    _CHAT_RETRY_DELAYS = (1, 2, 4)
    _TRANSIENT_ERROR_MARKERS = (
        "429",
        "rate limit",
        "500",
        "502",
        "503",
        "504",
        "overloaded",
        "timeout",
        "timed out",
        "connection",
        "server error",
        "temporarily unavailable",
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        default_model: str = "deepseek-chat",
        completion_fn: Optional[CompletionFn] = None,
        stream_fn: Optional[StreamFn] = None,
    ) -> None:
        """初始化 LLM 客户端。

        Args:
            api_key: API Key。
            api_base: API Base。
            default_model: 默认模型名称。
            completion_fn: 完成请求的异步函数。
            stream_fn: 流式请求的异步生成器函数。
        """
        self.api_key = api_key
        self.api_base = api_base
        self.default_model = default_model
        self.generation = GenerationSettings()
        self._completion_fn = completion_fn
        self._stream_fn = stream_fn

    def supports_stream(self) -> bool:
        return self._stream_fn is not None

    def stream_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        tool_choice: Optional[Dict[str, Any] | str] = None,
    ) -> Tuple[AsyncGenerator[StreamEvent, None], Awaitable[LLMResponse]]:
        loop = asyncio.get_running_loop()
        response_future: asyncio.Future[LLMResponse] = loop.create_future()

        async def _gen() -> AsyncGenerator[StreamEvent, None]:
            try:
                if self._stream_fn is None:
                    response = await self.chat(
                        messages=messages,
                        tools=tools,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        reasoning_effort=reasoning_effort,
                        tool_choice=tool_choice,
                    )
                    if response.content:
                        yield {"type": "text_delta", "data": {"content": response.content}}
                    response_future.set_result(response)
                    return

                payload = self._build_payload(
                    messages=messages,
                    tools=tools,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                    tool_choice=tool_choice,
                )
                content_parts: List[str] = []
                tool_call_buffers: Dict[int, Dict[str, Any]] = {}
                usage: Dict[str, int] = {}
                finish_reason: Optional[str] = None

                async for chunk in self._stream_fn(**payload):
                    delta = self._extract_delta_text(chunk)
                    usage_chunk = self._extract_usage(chunk)
                    if usage_chunk:
                        usage = usage_chunk
                    if delta:
                        content_parts.append(delta)
                        event: StreamEvent = {"type": "text_delta", "data": {"content": delta}}
                        if usage_chunk:
                            event["data"]["usage"] = usage_chunk
                        yield event

                    choices = self._get_value(chunk, "choices") or []
                    if choices:
                        choice = choices[0]
                        choice_finish = self._get_value(choice, "finish_reason")
                        if choice_finish:
                            finish_reason = choice_finish
                        delta_obj = self._get_value(choice, "delta") or {}
                        delta_tool_calls = self._get_value(delta_obj, "tool_calls") or []
                        for tc in delta_tool_calls:
                            index = self._get_value(tc, "index")
                            try:
                                index = int(index) if index is not None else 0
                            except Exception:
                                index = 0
                            buf = tool_call_buffers.setdefault(
                                index, {"id": None, "name": "", "arguments": ""}
                            )
                            tc_id = self._get_value(tc, "id")
                            if tc_id:
                                buf["id"] = tc_id
                            function = self._get_value(tc, "function") or {}
                            name = self._get_value(function, "name")
                            if name:
                                buf["name"] = name
                            args_delta = self._get_value(function, "arguments")
                            if isinstance(args_delta, str):
                                buf["arguments"] += args_delta

                tool_calls: List[ToolCallRequest] = []
                for _, buf in sorted(tool_call_buffers.items()):
                    args_value = buf.get("arguments") or ""
                    parsed_args: Dict[str, Any] = {}
                    if isinstance(args_value, str):
                        if args_value:
                            try:
                                parsed_args = json.loads(args_value)
                            except json.JSONDecodeError:
                                parsed_args = {}
                    elif isinstance(args_value, dict):
                        parsed_args = args_value
                    tool_calls.append(
                        ToolCallRequest(
                            id=buf.get("id") or _short_tool_id(),
                            name=buf.get("name") or "",
                            arguments=parsed_args,
                        )
                    )

                response = LLMResponse(
                    content="".join(content_parts) if content_parts else None,
                    tool_calls=tool_calls,
                    finish_reason=finish_reason or "stop",
                    usage=usage,
                )
                response_future.set_result(response)
            except Exception as exc:
                if not response_future.done():
                    response_future.set_result(
                        LLMResponse(content=f"Error calling LLM: {exc}", finish_reason="error")
                    )
                return

        return _gen(), response_future

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        tool_choice: Optional[Dict[str, Any] | str] = None,
    ) -> LLMResponse:
        """发送对话请求并返回解析后的响应。"""
        return await self._chat_with_retry(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        tool_choice: Optional[Dict[str, Any] | str] = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """流式请求并产出响应片段。"""
        if self._stream_fn is None:
            yield await self.chat(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
            )
            return

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )
        async for chunk in self._stream_fn(**payload):
            yield self._parse_response(chunk)

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        tool_choice: Optional[Dict[str, Any] | str] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """流式输出 Token/Delta 事件。"""
        if self._stream_fn is None:
            response = await self.chat(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
            )
            if response.content:
                yield {"type": "text_delta", "data": {"content": response.content}}
            return

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )
        async for chunk in self._stream_fn(**payload):
            delta = self._extract_delta_text(chunk)
            if not delta:
                usage = self._extract_usage(chunk)
                if usage:
                    yield {"type": "text_delta", "data": {"content": "", "usage": usage}}
                continue
            event: StreamEvent = {"type": "text_delta", "data": {"content": delta}}
            usage = self._extract_usage(chunk)
            if usage:
                event["data"]["usage"] = usage
            yield event

    async def _chat_with_retry(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        model: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
        reasoning_effort: Optional[str],
        tool_choice: Optional[Dict[str, Any] | str],
    ) -> LLMResponse:
        """带重试的对话调用。"""
        for attempt, delay in enumerate(self._CHAT_RETRY_DELAYS, start=1):
            response = await self._call_chat(
                messages=messages,
                tools=tools,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
            )
            if response.finish_reason != "error":
                return response
            if not self._is_transient_error(response.content):
                return response
            if delay:
                await asyncio.sleep(delay)

        return await self._call_chat(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )

    async def _call_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        model: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
        reasoning_effort: Optional[str],
        tool_choice: Optional[Dict[str, Any] | str],
    ) -> LLMResponse:
        """执行一次对话调用。"""
        if self._completion_fn is None:
            return LLMResponse(content="Error calling LLM: completion_fn not configured", finish_reason="error")

        payload = self._build_payload(
            messages=messages,
            tools=tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
        )
        try:
            raw = await self._completion_fn(**payload)
            return self._parse_response(raw)
        except Exception as exc:
            return LLMResponse(content=f"Error calling LLM: {exc}", finish_reason="error")

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        model: Optional[str],
        max_tokens: Optional[int],
        temperature: Optional[float],
        reasoning_effort: Optional[str],
        tool_choice: Optional[Dict[str, Any] | str],
    ) -> Dict[str, Any]:
        """构造请求参数。"""
        cleaned = self._sanitize_messages(self._sanitize_empty_content(messages))
        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": cleaned,
            "max_tokens": max(1, max_tokens or self.generation.max_tokens),
            "temperature": temperature if temperature is not None else self.generation.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        elif self.generation.reasoning_effort is not None:
            payload["reasoning_effort"] = self.generation.reasoning_effort
        if self.api_key:
            payload["api_key"] = self.api_key
        if self.api_base:
            payload["api_base"] = self.api_base
        return payload

    @classmethod
    def _is_transient_error(cls, content: Optional[str]) -> bool:
        """判断是否为可重试的瞬态错误。"""
        err = (content or "").lower()
        return any(marker in err for marker in cls._TRANSIENT_ERROR_MARKERS)

    def _parse_response(self, response: Any) -> LLMResponse:
        """解析 LLM 响应为统一格式。"""
        if response is None:
            return LLMResponse(content="Error calling LLM: empty response", finish_reason="error")

        if isinstance(response, LLMResponse):
            return response

        choices = self._get_value(response, "choices")
        if not choices:
            error = self._get_value(response, "error")
            if isinstance(error, dict):
                message = error.get("message") or str(error)
            else:
                message = str(error) if error else "Error calling LLM: missing choices"
            return LLMResponse(content=message, finish_reason="error")

        content: Optional[str] = None
        finish_reason: Optional[str] = None
        raw_tool_calls: List[Any] = []
        reasoning_content: Optional[str] = None
        thinking_blocks: Optional[List[Dict[str, Any]]] = None

        for choice in choices:
            message = self._get_value(choice, "message") or {}
            msg_content = self._get_value(message, "content")
            if content is None and msg_content:
                content = msg_content
            choice_finish = self._get_value(choice, "finish_reason")
            if finish_reason is None and choice_finish:
                finish_reason = choice_finish
            tool_calls = self._get_value(message, "tool_calls")
            if tool_calls:
                raw_tool_calls.extend(tool_calls)
            if reasoning_content is None:
                reasoning_content = self._get_value(message, "reasoning_content")
            if thinking_blocks is None:
                thinking_blocks = self._get_value(message, "thinking_blocks")

        tool_calls = []
        for tc in raw_tool_calls:
            function = self._get_value(tc, "function") or {}
            name = self._get_value(function, "name") or ""
            args = self._get_value(function, "arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if args is None:
                args = {}
            tool_call_id = self._get_value(tc, "id") or _short_tool_id()
            tool_calls.append(
                ToolCallRequest(
                    id=tool_call_id,
                    name=name,
                    arguments=args,
                    provider_specific_fields=self._get_value(tc, "provider_specific_fields"),
                    function_provider_specific_fields=self._get_value(function, "provider_specific_fields"),
                )
            )

        usage = self._extract_usage(response)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )

    def _extract_usage(self, response: Any) -> Dict[str, int]:
        """提取 token 使用量。"""
        usage = self._get_value(response, "usage")
        if not usage:
            return {}
        if isinstance(usage, dict):
            return {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            }
        return {}

    def _extract_delta_text(self, response: Any) -> str:
        """解析流式响应中的文本 delta。"""
        choices = self._get_value(response, "choices")
        if not choices:
            return ""
        choice = choices[0]
        delta = self._get_value(choice, "delta") or {}
        content = self._get_value(delta, "content")
        if content:
            return content
        message = self._get_value(choice, "message") or {}
        content = self._get_value(message, "content")
        return content or ""

    def _sanitize_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清理消息字段并规范 tool_call_id。"""
        sanitized = self._sanitize_request_messages(messages)
        id_map: Dict[str, str] = {}

        def map_id(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            return id_map.setdefault(value, self._normalize_tool_call_id(value))

        for msg in sanitized:
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                normalized = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        normalized.append(tc)
                        continue
                    tc_clean = dict(tc)
                    tc_clean["id"] = map_id(tc_clean.get("id"))
                    normalized.append(tc_clean)
                msg["tool_calls"] = normalized

            if "tool_call_id" in msg and msg["tool_call_id"]:
                msg["tool_call_id"] = map_id(msg["tool_call_id"])

        return sanitized

    def _sanitize_request_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """剔除非标准字段并补齐 assistant content。"""
        sanitized = []
        for msg in messages:
            clean = {k: v for k, v in msg.items() if k in _ALLOWED_MSG_KEYS}
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            sanitized.append(clean)
        return sanitized

    def _sanitize_empty_content(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """避免空内容导致 provider 报错。"""
        result: List[Dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str) and not content:
                clean = dict(msg)
                clean["content"] = None if (msg.get("role") == "assistant" and msg.get("tool_calls")) else "(empty)"
                result.append(clean)
                continue
            if isinstance(content, list):
                filtered = [
                    item
                    for item in content
                    if not (
                        isinstance(item, dict)
                        and item.get("type") in ("text", "input_text", "output_text")
                        and not item.get("text")
                    )
                ]
                if len(filtered) != len(content):
                    clean = dict(msg)
                    if filtered:
                        clean["content"] = filtered
                    elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                        clean["content"] = None
                    else:
                        clean["content"] = "(empty)"
                    result.append(clean)
                    continue
            if isinstance(content, dict):
                clean = dict(msg)
                clean["content"] = [content]
                result.append(clean)
                continue
            result.append(msg)
        return result

    @staticmethod
    def _normalize_tool_call_id(tool_call_id: Any) -> Any:
        """将 tool_call_id 归一化为 9 位字母数字。"""
        if not isinstance(tool_call_id, str):
            return tool_call_id
        return tool_call_id

    @staticmethod
    def _get_value(obj: Any, key: str) -> Any:
        """从 dict 或对象中读取字段。"""
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

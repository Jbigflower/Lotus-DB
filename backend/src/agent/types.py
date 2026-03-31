from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Agent 角色枚举。"""

    MAIN = "main"
    DELEGATED = "delegated"
    SPECIALIST = "specialist"


@dataclass
class LoopState:
    """循环过程中的可变状态。"""

    messages: List[Dict[str, Any]]
    iteration: int = 0
    tool_calls_made: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "running"


@dataclass
class AgentResult:
    """智能体执行的结果对象。"""

    output: str
    state: LoopState
    config: "AgentConfig"


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果，用结构化对象替代 (str, Optional[str]) 元组。"""

    output: str
    error: Optional[str] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


class ToolFunctionCall(BaseModel):
    """OpenAI tools 的函数调用载体。"""

    name: str = Field(..., description="工具函数名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数对象")


class ToolCall(BaseModel):
    """OpenAI tools 的工具调用对象。"""

    id: str = Field(..., description="工具调用 ID")
    type: Literal["function"] = "function"
    function: ToolFunctionCall = Field(..., description="函数调用信息")


class Message(BaseModel):
    """对齐 OpenAI messages 结构的消息模型。"""

    role: Literal["system", "user", "assistant", "tool"] = Field(..., description="消息角色")
    content: Optional[str] = Field(None, description="消息内容")
    tool_calls: Optional[List[ToolCall]] = Field(None, description="assistant 的工具调用列表")
    name: Optional[str] = Field(None, description="tool 消息工具名称")
    tool_call_id: Optional[str] = Field(None, description="tool 消息对应的调用 ID")

    def to_llm_dict(self) -> Dict[str, Any]:
        """转换为 LLM Provider 接受的消息字典。"""

        d: Dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.role == "assistant" and self.tool_calls:
            def _serialize_tool_args(value: Any) -> str:
                if value is None:
                    return "{}"
                if isinstance(value, str):
                    return value
                try:
                    return json.dumps(value, ensure_ascii=False)
                except (TypeError, ValueError):
                    return "{}"

            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": _serialize_tool_args(tc.function.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.role == "tool":
            if self.tool_call_id is not None:
                d["tool_call_id"] = self.tool_call_id
            if self.name is not None:
                d["name"] = self.name
            if self.content is None:
                d["content"] = ""
        return d


@dataclass
class RequestContext:
    """请求级上下文，用于跨模块传递。"""

    user_id: str
    session_id: str
    trace_id: str


class StreamEvent(TypedDict):
    """统一的流式事件协议。"""

    type: Literal["text_delta", "tool_start", "tool_end", "error", "done", "thinking"]
    data: Dict[str, Any]


class ConversationHistory:
    """纯内存对话历史容器。"""

    def __init__(self) -> None:
        """初始化空的对话历史。"""

        self._messages: List[Message] = []

    def add(self, message: Message) -> None:
        """追加一条消息。"""

        self._messages.append(message)

    def get_recent(self, n: int) -> List[Message]:
        """获取最近 n 条消息。"""

        return self._messages[-n:] if n > 0 else []

    def to_llm_messages(self) -> List[Dict[str, Any]]:
        """转换为 LLM Provider 的消息数组。"""

        return [m.to_llm_dict() for m in self._messages]



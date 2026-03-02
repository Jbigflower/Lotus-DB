import asyncio
from typing import Annotated, TypedDict, List, Dict, Any, Literal, Optional
from pathlib import Path
from langchain_core.messages import BaseMessage, AIMessage, trim_messages
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.types import interrupt, Command
from langgraph.prebuilt import ToolNode
from src.agent.tools.factory import ToolFactory
from src.agent.utils.MongoDBStore import MongoDBStore

# 1. 定义增强型状态
class EnhancedState(MessagesState):
    messages: Annotated[list[BaseMessage], "add_messages"]
    user_info: Dict[str, Any]      # 存储 profile, preferences, background
    step_count: int               # 失控保护计数器
    prompt_version: str           # 记录当前使用的 Prompt 版本
    requires_auth: bool           # 业务门控标识

class LotusReActAugmentAgent:
    def __init__(self, model, tool_factory: ToolFactory, store: Optional[MongoDBStore] = None):
        self.model = model
        self.tool_factory = tool_factory
        self.store = store
        self.recursion_limit = 25  # 官方失控保护：最大步数
        self.tools = self.tool_factory.get_tools_for_agent("db_expert")
        self.tool_node = ToolNode(self.tools)
        self.agent_graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(EnhancedState)
        
        builder.add_node("preprocess", self._preprocess_node)
        builder.add_node("agent", self._call_model_node)
        builder.add_node("action_gate", self._gatekeeper_node) # 风控门控
        builder.add_node("tools", self._execute_tools_node)
        
        builder.add_edge(START, "preprocess")
        builder.add_edge("preprocess", "agent")
        
        # 逻辑：Agent -> 门控 -> (中断或继续) -> 执行工具 -> Agent
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "action_gate", "end": END}
        )
        builder.add_edge("action_gate", "tools")
        builder.add_edge("tools", "agent")
        return builder.compile()

    # --- 核心功能节点实现 ---

    async def _preprocess_node(self, state: EnhancedState):
        """1. 上下文准备：拉取版本化 Prompt + 加载用户记忆"""
        version = str(state.get("prompt_version", "1.0"))
        prompt = self._read_prompt_file(version)
        # 记忆加载 (user_profile, user_preferences)
        return {"user_info": {"active_prompt": prompt, "context_text": state['user_info']}} 

    async def _call_model_node(self, state: EnhancedState):
        msgs = state.get("messages") or []
        if not msgs:
            return {"messages": [AIMessage(content="未提供输入内容，请重新提问。")], "step_count": state.get("step_count", 0)}
        try:
            trimmed = trim_messages(
                msgs,
                max_tokens=2000,
                strategy="last",
                token_counter=self.model,
                start_on="human"
            )
        except NotImplementedError:
            try:
                trimmed = trim_messages(
                    msgs,
                    max_tokens=2000,
                    strategy="last",
                    token_counter="approximate",
                    start_on="human"
                )
            except Exception:
                trimmed = msgs[-10:] if len(msgs) > 10 else msgs
        if not trimmed:
            return {"messages": [AIMessage(content="未提供有效对话上下文，请重新提问。")], "step_count": state.get("step_count", 0)}
        llm_with_skills = self.model.bind_tools(self.tools)
        
        response = await llm_with_skills.ainvoke(trimmed)
        return {"messages": [response], "step_count": state.get("step_count", 0) + 1}

    async def _gatekeeper_node(self, state: EnhancedState):
        """3. 安全风险加固：业务门控 (HITL)"""
        last_message = state["messages"][-1]
        
        # 检查是否包含风险工具调用 (requires_confirmation)
        tool_calls = getattr(last_message, "tool_calls", None) or []
        for tool_call in tool_calls:
            name = getattr(tool_call, "name", None)
            args = getattr(tool_call, "args", None)
            if name is None and isinstance(tool_call, dict):
                name = tool_call.get("name")
                args = tool_call.get("args")
            if name in ["delete_library", "wipe_all_data"]:
                # 触发 LangGraph 中断，等待人工确认
                # 前端会收到这个中断请求，用户点击确认后继续
                confirm = interrupt({
                    "action": "confirmation_required",
                    "tool": name,
                    "params": args
                })
                
                if not confirm.get("approved"):
                    raise Exception("用户拒绝了风险操作")
        
        return state

    async def _execute_tools_node(self, state: EnhancedState):
        """4. 失控保护：检查调用上限"""
        if state["step_count"] > 10: # 自定义工具调用上限
            return {"messages": [AIMessage(content="已达到最大任务执行上限，请尝试拆分问题。")]}
        return await self.tool_node.ainvoke(state)

    def _should_continue(self, state: EnhancedState):
        """路由决策"""
        messages = state.get("messages") or []
        if not messages:
            return "end"
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "continue"
        return "end"

    def get_graph(self):
        return self.agent_graph

    def _read_prompt_file(self, version: str) -> str:
        base = Path(__file__).resolve().parent.parent / "prompts" / "react_augment"
        candidates = [
            base / f"react-v{version}.txt",
            base / "react-v1.0.txt",
        ]
        for p in candidates:
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    continue
        return ""

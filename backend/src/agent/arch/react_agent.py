from typing import Annotated, TypedDict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from src.agent.tools.factory import ToolFactory
from config.setting import get_settings

settings = get_settings()


class ReactState(MessagesState):
    step_count: int


class LotusReActAgent:
    def __init__(self, model: str = "deepseek-chat"):
        self.tools = ToolFactory.get_tools_for_agent("simple_react")
        if "deepseek" in model:
            self.llm = ChatOpenAI(
                model=model,
                base_url="https://api.deepseek.com",
                api_key=settings.llm.deepseek_api_key,
                streaming=True,
            )
        else:
            self.llm = ChatOpenAI(model=model, streaming=True)

        self.tool_node = ToolNode(self.tools)
        self.agent_graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(ReactState)
        builder.add_node("agent", self._call_model_node)
        builder.add_node("tools", self.tool_node)
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {"continue": "tools", "end": END},
        )
        builder.add_edge("tools", "agent")
        return builder.compile()

    async def _call_model_node(self, state: ReactState):
        msgs = state.get("messages") or []
        print(state)
        if not msgs:
            return {"messages": [AIMessage(content="未提供输入内容，请重新提问。")], "step_count": state.get("step_count", 0)}
        llm_with_tools = self.llm.bind_tools(self.tools)
        response = await llm_with_tools.ainvoke(msgs)
        return {"messages": [response], "step_count": state.get("step_count", 0) + 1}

    def _should_continue(self, state: ReactState):
        messages = state.get("messages") or []
        if not messages:
            return "end"
        last = messages[-1]
        if getattr(last, "tool_calls", None):
            return "continue"
        return "end"

    def get_graph(self):
        return self.agent_graph

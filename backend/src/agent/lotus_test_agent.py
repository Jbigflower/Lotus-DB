from typing import Optional
from functools import cached_property
from mongomock_motor import AsyncMongoMockClient
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from src.agent.lotus_agent import LotusDBAgent, AgentState
from src.agent.utils.MongoDBStore import MongoDBStore
from src.agent.utils.AsyncMongoDBSaver import AsyncMongoDBSaver


class LotusTestAgent(LotusDBAgent):
    """
    Test version of LotusDBAgent that uses mongomock for isolation.
    Ensures all DB operations (including LangGraph checkpoints) are in the mock environment.
    """
    TEST_SYSTEM_PROMPT = (
        "当用户要求创建电影、书籍或媒体记录时：\n"
        "若缺少元数据，优先调用搜索类工具自动补全。\n"
        "不主动向用户请求可通过工具获得的信息。\n"
        "只有在工具无法提供数据时才询问用户。\n"
        "除删除类敏感操作外，不进行多轮确认。\n"
        "以“完成任务”为最高优先级。"
    )

    def __init__(self, client: Optional[object] = None):
        self._injected_client = client
        super().__init__()

    @cached_property
    def client(self):
        if self._injected_client:
            return self._injected_client
        return AsyncMongoMockClient()

    @cached_property
    def checkpointer(self):
        return AsyncMongoDBSaver(self.client, db_name=self.db_name)

    @cached_property
    def store(self):
        return MongoDBStore(self.client, db_name=self.db_name)

    @cached_property
    def graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("router", self._router_node_with_system_prompt)
        workflow.add_node("react", self._react_node)
        workflow.add_node("react_augment", self._react_augment_node)
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("orchestrator", self._orchestrator_node)

        workflow.add_edge(START, "router")
        workflow.add_conditional_edges("router", self._route_to_agent)
        workflow.add_node("finalize", self._finalize_node)
        workflow.add_edge("react", "finalize")
        workflow.add_edge("react_augment", "finalize")
        workflow.add_edge("plan", END)
        workflow.add_edge("orchestrator", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _router_node_with_system_prompt(self, state: AgentState):
        query = state.get("query") or ""
        if not query:
            return {}
        return {
            "messages": [
                SystemMessage(content=self.TEST_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
        }

import os
from typing import Annotated, TypedDict, Dict, Any, Generator, AsyncGenerator, List, Optional
from functools import cached_property
from datetime import datetime, timezone
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.runtime import Runtime
from langgraph.types import Command
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from src.db.mongo_db import get_mongo_client
from config.setting import get_settings
from fastapi import HTTPException
from langchain_openai import ChatOpenAI
from src.agent.tools.factory import ToolFactory
from src.agent.utils.MongoDBStore import MongoDBStore
from src.agent.utils.AsyncMongoDBSaver import AsyncMongoDBSaver
from pymongo import MongoClient
from src.logic.users.user_logic import UserLogic

from .arch.react_agent import LotusReActAgent
from .arch.react_augment_agent import LotusReActAugmentAgent

settings = get_settings()


class AgentState(MessagesState):
    query: str
    user_id: str
    agent_selection: str
    final_response: str


class LotusDBAgent:
    def __init__(self):
        self.db_name = settings.llm.langraph_db_name
        self.agent_versions = set(['React base', 'Plan base', 'Orchestrator base', 'React Augment'])
        self.react_agent = LotusReActAgent()
        self.react_augment_agent = LotusReActAugmentAgent(
            model=ChatOpenAI(
                model="deepseek-chat",
                base_url="https://api.deepseek.com",
                api_key=settings.llm.deepseek_api_key,
                streaming=True,
            ),
            tool_factory=ToolFactory,
            store=self.store
        )

    @cached_property
    def client(self):
        return get_mongo_client()

    @cached_property
    def checkpointer(self):
        return AsyncMongoDBSaver(self.client, db_name=self.db_name)

    @cached_property
    def store(self):
        return MongoDBStore(self.client, db_name=self.db_name)

    @cached_property
    def graph(self):
        return self._build_graph()

    # @cached_property
    # def sync_client(self):
    #     db = settings.database
    #     return MongoClient(db.mongo_url, serverSelectionTimeoutMS=5000)

    @cached_property
    def user_logic(self):
        return UserLogic()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("router", self._router_node)
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

    def _router_node(self, state: AgentState):
        query = state.get("query") or ""
        if query:
            return {"messages": [HumanMessage(content=query)]}
        return {}

    def _route_to_agent(self, state: AgentState):
        selection = (state.get("agent_selection") or "react").lower()
        if selection in ("react_augment", "augment", "react-augment"):
            return "react_augment"
        if selection in ("plan",):
            return "plan"
        if selection in ("orchestrator", "orch"):
            return "orchestrator"
        return "react"

    def _plan_node(self, state: AgentState):
        return {"final_response": "Plan: 复杂任务已拆解执行"}

    def _orchestrator_node(self, state: AgentState):
        return {"final_response": "Orchestrator: 协调多 Agent 结果完成"}

    def _finalize_node(self, state: AgentState):
        msgs = state.get("messages") or []
        text = ""
        if msgs:
            last = msgs[-1]
            try:
                text = getattr(last, "content", "") or ""
            except Exception:
                text = ""
        return {"final_response": text}

    async def _react_node(self, state: AgentState, config: RunnableConfig, context: Optional[Dict[str, Any]] = None):
        current_messages = state.get("messages") or []
        react_state = {"messages": current_messages, "step_count": state.get("step_count", 0)}
        out = await self.react_agent.get_graph().ainvoke(react_state, config=config, context=context)
        return {"messages": out.get("messages", [])}

    async def _react_augment_node(self, state: AgentState, config: RunnableConfig, context: Optional[Dict[str, Any]] = None):
        uid = state.get("user_id") or ""
        profile = await self.store.get(("users", uid), "profile") if uid else None
        preferences = await self.store.get(("users", uid), "preferences") if uid else None
        user_info = {
            "user profile": profile or {},
            "user preferences": preferences or {},
            "user background": (profile or {}).get("bio") or (profile or {}).get("background") or ""
        }
        enhanced_state = {
            "messages": state.get("messages") or [],
            "user_info": user_info,
            "prompt_version": state.get("prompt_version", "1.0"),
            "step_count": state.get("step_count", 0),
            "requires_auth": False,
        }
        out = await self.react_augment_agent.get_graph().ainvoke(enhanced_state, config=config, context=context)
        return {"messages": out.get("messages", [])}

    async def ainvoke(self, query: str, user_id: str, thread_id: str, agent_selection: Optional[str] = None):
        now = datetime.now(timezone.utc)
        
        current_user = None
        try:
            current_user = await self.user_logic.get_user(user_id)
        except Exception as e:
            print(f"DEBUG: Failed to get user: {e}")
            current_user = None

        print(f"DEBUG: Agent ainvoke current_user: {current_user}")

        config = {
            "configurable": {
                "thread_id": thread_id, 
                "user": user_id,
                "user_object": current_user.model_dump() if current_user else None,
            },
            "metadata": {"user_id": user_id, "query": query, "updated_at": now.isoformat()},
        }
        print(f"DEBUG: Agent ainvoke config user_object: {config['configurable']['user_object']}")
        inputs = {"query": query, "user_id": user_id}
        if agent_selection:
            inputs["agent_selection"] = agent_selection
        
        context = {"user": current_user, "user_id": user_id}
        return await self.graph.ainvoke(inputs, config=config, context=context)

    async def astream(self, query: str, user_id: str, thread_id: str):
        now = datetime.now(timezone.utc)
        config = {
            "configurable": {"thread_id": thread_id, "user": user_id},
            "metadata": {"user_id": user_id, "query": query, "updated_at": now.isoformat()},
        }
        inputs = {"query": query, "user_id": user_id}
        current_user = None
        try:
            current_user = await self.user_logic.get_user(user_id)
        except Exception:
            current_user = None
        context = {"user": current_user, "user_id": user_id}

        emitted = False

        def extract_text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                direct = value.get("content")
                if isinstance(direct, str) and direct:
                    return direct
                msg = value.get("message")
                if isinstance(msg, dict):
                    msg_text = msg.get("content")
                    if isinstance(msg_text, str) and msg_text:
                        return msg_text
            try:
                content = getattr(value, "content", "")
                return str(content or "")
            except Exception:
                return ""

        async for event in self.graph.astream_events(
            inputs,
            config=config,
            context=context,
            version="v1"
        ):
            event_type = event.get("event")
            data = event.get("data") or {}
            if event_type == "on_chat_model_stream":
                text = extract_text(data.get("chunk"))
                if text:
                    emitted = True
                    yield text
            elif event_type == "on_chat_model_end" and not emitted:
                text = extract_text(data.get("output"))
                if text:
                    emitted = True
                    yield text

    async def delete_chat(self, thread_id: str):
        await self.checkpointer.adelete_thread(thread_id=thread_id)
        return {"status": "success", "thread_id": thread_id}

    async def verify_ownership(self, thread_id: str, user_id: str):
        config = {"configurable": {"thread_id": thread_id}}
        state = await self.graph.aget_state(config)
        if not state.values:
            return True
        stored_user_id = state.metadata.get("user_id")
        if stored_user_id and stored_user_id != user_id:
            raise HTTPException(status_code=403, detail="Permission denied")
        return True

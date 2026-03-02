from typing import List, Optional, AsyncGenerator
import json
from uuid import uuid4
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from src.services.llm.llm_service import LLMService
from src.core.handler import router_handler
from src.core.dependencies import get_current_user
from config.logging import get_router_logger
from config.setting import get_settings

router = APIRouter(prefix="/api/v1/llm", tags=["LLM"])
llm_service = LLMService()
logger = get_router_logger("llm")

class ChatRequest(BaseModel):
    query: str = Field(...)
    thread_id: Optional[str] = None
    agent_version: str = Field("React base")

class ChatResponse(BaseModel):
    final_response: str
    thread_id: str

class ThreadSummary(BaseModel):
    thread_id: str
    last_updated: Optional[str] = None
    preview: Optional[str] = None

class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None

class ThreadDetail(BaseModel):
    thread_id: str
    messages: List[ChatMessageOut]
    last_updated: Optional[str] = None
    preview: Optional[str] = None

class LangsmithInfo(BaseModel):
    enabled: bool
    ui_url: str
    project: Optional[str] = None

async def get_user_id(current_user = Depends(get_current_user)) -> str:
    if hasattr(current_user, "id"):
        return str(current_user.id)
    if isinstance(current_user, dict) and "id" in current_user:
        return str(current_user["id"])
    return "user_default"

@router.post("/chat", response_model=ChatResponse)
@router_handler(action="chat_with_agent")
async def chat_with_agent(body: ChatRequest, request: Request, user_id: str = Depends(get_user_id)):
    thread_id = body.thread_id or str(uuid4())
    result = None
    async for r in llm_service.chat(
        query=body.query,
        user_id=user_id,
        thread_id=thread_id,
        Agent_version=body.agent_version,
        stream=False
    ):
        result = r
        break
    final = ""
    if isinstance(result, dict):
        final = str(result.get("final_response") or "")
        if not final:
            msgs = result.get("messages")
            if isinstance(msgs, list) and msgs:
                last = msgs[-1]
                try:
                    final = getattr(last, "content", "") or ""
                except Exception:
                    try:
                        final = last.get("content", "")
                    except Exception:
                        final = ""
    return ChatResponse(final_response=final, thread_id=thread_id)

@router.post("/chat/stream")
@router_handler(action="chat_with_agent_stream")
async def chat_with_agent_stream(body: ChatRequest, request: Request, user_id: str = Depends(get_user_id)):
    thread_id = body.thread_id or str(uuid4())
    async def gen() -> AsyncGenerator[bytes, None]:
        yield (json.dumps({"type": "id", "content": thread_id}) + "\n").encode("utf-8")
        def extract_text(value) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                direct = value.get("final_response")
                if isinstance(direct, str) and direct:
                    return direct
                msgs = value.get("messages")
                if isinstance(msgs, list) and msgs:
                    return extract_text(msgs[-1])
                for v in value.values():
                    text = extract_text(v)
                    if text:
                        return text
                return ""
            if isinstance(value, (list, tuple)):
                for v in value:
                    text = extract_text(v)
                    if text:
                        return text
                return ""
            try:
                content = getattr(value, "content", "")
                return str(content or "")
            except Exception:
                return ""

        accumulated = ""
        async for r in llm_service.chat(
            query=body.query,
            user_id=user_id,
            thread_id=thread_id,
            Agent_version=body.agent_version,
            stream=True
        ):
            text = extract_text(r)
            if not text:
                continue
            if accumulated and text.startswith(accumulated):
                delta = text[len(accumulated):]
                accumulated = text
            else:
                delta = text
                accumulated = text
            if delta:
                yield (json.dumps({"type": "text", "content": delta}) + "\n").encode("utf-8")
    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.get("/threads", response_model=List[ThreadSummary])
@router_handler(action="list_threads")
async def list_threads(user_id: str = Depends(get_user_id)) -> List[ThreadSummary]:
    data = await llm_service.get_user_history_list(user_id)
    return [ThreadSummary(**i) for i in data]

@router.get("/threads/{thread_id}", response_model=ThreadDetail)
@router_handler(action="get_thread_detail")
async def get_thread_detail(thread_id: str, user_id: str = Depends(get_user_id)):
    data = await llm_service.get_thread_detail(user_id=user_id, thread_id=thread_id)
    msgs = [ChatMessageOut(**m) for m in data.get("messages", [])]
    return ThreadDetail(
        thread_id=data.get("thread_id"),
        messages=msgs,
        last_updated=data.get("last_updated"),
        preview=data.get("preview")
    )

@router.delete("/threads/{thread_id}")
@router_handler(action="delete_thread")
async def delete_thread(thread_id: str, user_id: str = Depends(get_user_id)):
    await llm_service.delete_chat(user_id=user_id, thread_id=thread_id)
    return {"status": "success"}

@router.get("/langsmith/info", response_model=LangsmithInfo)
@router_handler(action="get_langsmith_info")
async def get_langsmith_info(user_id: str = Depends(get_user_id)):
    s = get_settings().llm
    enabled = bool(s.langsmith_tracing and s.langsmith_api_key)
    ep = s.langsmith_endpoint or "https://api.smith.langchain.com"
    ui = ep.replace("api.", "")
    return LangsmithInfo(enabled=enabled, ui_url=ui, project=s.langsmith_project)

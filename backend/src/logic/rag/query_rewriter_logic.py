from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from config.setting import settings
from src.agent.llm.provider import LLMClient

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

def _build_llm(model_name: Optional[str] = None) -> LLMClient:
    """构建用于查询重写的 LLM 客户端"""
    if AsyncOpenAI is None:
        raise ImportError("openai is not installed, but it is required for LLMClient.")
    
    client = AsyncOpenAI(api_key=settings.llm.deepseek_api_key, base_url=settings.llm.deepseek_base_url)
    
    async def completion_fn(**kwargs: Any):
        kwargs.pop("api_key", None)
        kwargs.pop("api_base", None)
        return await client.chat.completions.create(**kwargs)

    return LLMClient(
        api_key=settings.llm.deepseek_api_key,
        api_base=settings.llm.deepseek_base_url,
        default_model=model_name or settings.llm.deepseek_model,
        completion_fn=completion_fn,
        stream_fn=None,
    )

class BaseQueryRewriter(ABC):
    """Abstract base class for query rewriters."""

    @abstractmethod
    async def rewrite(self, query: str) -> Dict[str, Any]:
        """
        Rewrite the user query.
        
        Args:
            query: The original user query.
            
        Returns:
            A dictionary containing the rewritten query and metadata.
            Example: {"normalized": "...", "original": "...", "type": "..."}
        """
        pass


class LLMQueryRewriter(BaseQueryRewriter):
    def __init__(self, model_name: str = None):
        self.llm = _build_llm(model_name)
        self.prompt_template = """You are an expert search query optimizer. Your task is to rewrite the user's query to be more effective for retrieval.
        
        Rules:
        1. Correct any spelling mistakes.
        2. Expand with relevant synonyms or related terms if necessary, but keep it concise.
        3. Remove unnecessary conversational filler (e.g., "please", "help me find").
        4. If the query is already good, output it as is.
        5. Output ONLY the rewritten query, no explanations.

        User Query: {query}
        Rewritten Query:"""

    async def rewrite(self, query: str) -> Dict[str, Any]:
        prompt = self.prompt_template.format(query=query)
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.chat(messages=messages, model=self.llm.default_model)
        rewritten = response.content or ""
        return {
            "original": query,
            "rewritten": rewritten.strip(),
            "type": "llm_rewrite"
        }


class HyDERewriter(BaseQueryRewriter):
    def __init__(self, model_name: str = None):
        self.llm = _build_llm(model_name)
        self.prompt_template = """Please write a passage to answer the question.
        Question: {query}
        Passage:"""

    async def rewrite(self, query: str) -> Dict[str, Any]:
        prompt = self.prompt_template.format(query=query)
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.chat(messages=messages, model=self.llm.default_model)
        hypothetical_document = response.content or ""
        return {
            "original": query,
            "rewritten": hypothetical_document.strip(),
            "type": "hyde"
        }


class MultiQueryRewriter(BaseQueryRewriter):
    def __init__(self, model_name: str = None, n: int = 3):
        self.n = n
        self.llm = _build_llm(model_name)
        self.prompt_template = """You are an AI language model assistant. Your task is to generate {n} different versions of the given user question to retrieve relevant documents from a vector database. 
        By generating multiple perspectives on the user question, your goal is to help the user overcome some of the limitations of the distance-based similarity search. 
        Provide these alternative questions separated by commas.
        Original question: {question}"""

    async def rewrite(self, query: str) -> Dict[str, Any]:
        prompt = self.prompt_template.format(n=self.n, question=query)
        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.chat(messages=messages, model=self.llm.default_model)
        content = response.content or ""
        
        # Ensure we have a list of strings
        queries = [q.strip() for q in content.split(",") if q.strip()]
        if not queries:
            queries = [query]
            
        return {
            "original": query,
            "queries": queries,
            "type": "multi_query"
        }


class StepBackRewriter(BaseQueryRewriter):
    """Placeholder for Step-Back Prompting query rewriter."""

    async def rewrite(self, query: str) -> Dict[str, Any]:
        raise NotImplementedError("StepBackRewriter is not implemented yet.")


class QueryRewriterFactory:
    @staticmethod
    def create_rewriter(type: str, **kwargs) -> Optional[BaseQueryRewriter]:
        if type == "llm":
            return LLMQueryRewriter(**kwargs)
        elif type == "hyde":
            return HyDERewriter(**kwargs)
        elif type == "multi_query":
            return MultiQueryRewriter(**kwargs)
        elif type == "step_back":
            return StepBackRewriter(**kwargs)
        else:
            return None

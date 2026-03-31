import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.logic.rag.query_rewriter_logic import (
    LLMQueryRewriter,
    HyDERewriter,
    MultiQueryRewriter,
    QueryRewriterFactory,
    StepBackRewriter
)
from src.logic.rag.reranker_logic import OllamaEncoderReranker, CrossEncoderReRanker
from src.logic.rag.searcher_logic import HybridSearcher
import pyarrow as pa
from src.repos.embedding_repos.base_lance_repo import BaseLanceRepo

# --- Query Rewriter Tests ---

@pytest.mark.asyncio
async def test_llm_query_rewriter():
    with patch("src.logic.rag.query_rewriter_logic.ChatOpenAI") as MockChatOpenAI:
        mock_llm = MockChatOpenAI.return_value
        # Mock the chain invocation
        # The chain is prompt | llm | output_parser
        # We need to mock the invoke/ainvoke of the chain. 
        # Since the chain is constructed in __init__, we might need to mock invoke on the chain object directly if possible, 
        # or mock the components.
        
        # A simpler way is to mock the chain attribute of the instance
        rewriter = LLMQueryRewriter(model_name="test-model")
        rewriter.chain = AsyncMock()
        rewriter.chain.ainvoke.return_value = "rewritten query"
        
        result = await rewriter.rewrite("original query")
        
        assert result["original"] == "original query"
        assert result["rewritten"] == "rewritten query"
        assert result["type"] == "llm_rewrite"
        rewriter.chain.ainvoke.assert_called_once_with({"query": "original query"})

@pytest.mark.asyncio
async def test_hyde_rewriter():
    with patch("src.logic.rag.query_rewriter_logic.ChatOpenAI") as MockChatOpenAI:
        rewriter = HyDERewriter(model_name="test-model")
        rewriter.chain = AsyncMock()
        rewriter.chain.ainvoke.return_value = "hypothetical document"
        
        result = await rewriter.rewrite("original query")
        
        assert result["original"] == "original query"
        assert result["rewritten"] == "hypothetical document"
        assert result["type"] == "hyde"

@pytest.mark.asyncio
async def test_multi_query_rewriter():
    with patch("src.logic.rag.query_rewriter_logic.ChatOpenAI") as MockChatOpenAI:
        rewriter = MultiQueryRewriter(model_name="test-model", n=3)
        rewriter.chain = AsyncMock()
        # Mock return value as list of strings
        rewriter.chain.ainvoke.return_value = ["q1", "q2", "q3"]
        
        result = await rewriter.rewrite("original query")
        
        assert result["original"] == "original query"
        assert result["queries"] == ["q1", "q2", "q3"]
        assert result["type"] == "multi_query"

def test_query_rewriter_factory():
    with patch("src.logic.rag.query_rewriter_logic.ChatOpenAI"):
        assert isinstance(QueryRewriterFactory.create_rewriter("llm"), LLMQueryRewriter)
        assert isinstance(QueryRewriterFactory.create_rewriter("hyde"), HyDERewriter)
        assert isinstance(QueryRewriterFactory.create_rewriter("multi_query"), MultiQueryRewriter)
        assert isinstance(QueryRewriterFactory.create_rewriter("step_back"), StepBackRewriter)
        assert QueryRewriterFactory.create_rewriter("unknown") is None

# --- Reranker Tests ---

def test_ollama_reranker_init():
    with patch("src.logic.rag.reranker_logic.ChatOpenAI"):
        reranker = OllamaEncoderReranker(model_name="test-model")
        assert reranker.text_col == "document"

# --- Searcher Tests ---

@pytest.mark.asyncio
async def test_hybrid_searcher_vector_only():
    mock_repo = MagicMock(spec=BaseLanceRepo)
    mock_repo.ensure_table_bound = AsyncMock()
    mock_repo._build_filter_conditions.return_value = []
    
    # Mock table.search().limit().to_arrow()
    mock_builder = MagicMock()
    mock_builder.limit.return_value = mock_builder
    
    # Create a dummy pyarrow table
    data = [
        {"id": "1", "vector": [0.1, 0.1], "_distance": 0.5},
        {"id": "2", "vector": [0.2, 0.2], "_distance": 0.3}
    ]
    schema = pa.schema([
        ("id", pa.string()),
        ("vector", pa.list_(pa.float32(), 2)),
        ("_distance", pa.float32())
    ])
    arrow_table = pa.Table.from_pylist(data, schema=schema)
    
    async def mock_to_arrow():
        return arrow_table
    
    mock_builder.to_arrow = mock_to_arrow
    
    # Mock search method on table
    mock_repo.table = MagicMock()
    # search needs to be awaitable if called with await, but lancedb table.search is synchronous builder usually, 
    # but in our code we await repo.table.search(vector, query_type="vector") ??
    # Checking hybrid_searcher.py: builder = await self.repo.table.search(...)
    # Wait, BaseLanceRepo.table is AsyncTable?
    # In base_lance_repo.py: self.table: Optional[AsyncTable] = None
    # AsyncTable.search is async? No, usually search returns a builder.
    # But in hybrid_searcher.py: builder = await self.repo.table.search(vector, query_type="vector")
    # This implies search is async.
    
    async def mock_search(*args, **kwargs):
        return mock_builder
    
    mock_repo.table.search = mock_search
    
    # Mock from_lance_record
    def mock_from_record(record):
        return {"id": record["id"], "val": "obj"}
    mock_repo.from_lance_record = mock_from_record

    searcher = HybridSearcher(mock_repo)
    
    results = await searcher.search(
        text="",
        vector=[0.1, 0.1],
        mode="dense",
        top_k=2
    )
    
    assert len(results) == 2
    # Check sorting: lower distance means higher score (1/(1+dist))
    # distance 0.3 -> score ~0.769
    # distance 0.5 -> score ~0.666
    # Should be sorted by score desc
    assert results[0]["item"]["id"] == "2"
    assert results[1]["item"]["id"] == "1"

@pytest.mark.asyncio
async def test_hybrid_searcher_rrf_merge():
    mock_repo = MagicMock(spec=BaseLanceRepo)
    searcher = HybridSearcher(mock_repo)
    
    list1 = [{"id": "A"}, {"id": "B"}]
    list2 = [{"id": "B"}, {"id": "C"}]
    
    merged = searcher._rrf_merge(list1, list2, k=1)
    
    # A: rank 0 in list1 -> score 1/(1+0+1) = 0.5
    # B: rank 1 in list1 -> 1/(1+1+1) = 0.33; rank 0 in list2 -> 0.5. Total = 0.833
    # C: rank 1 in list2 -> 0.33
    
    # Sort check
    merged.sort(key=lambda x: x["score"], reverse=True)
    
    assert merged[0]["id"] == "B"
    assert abs(merged[0]["score"] - 0.833) < 0.01
    assert merged[1]["id"] == "A"
    assert merged[2]["id"] == "C"

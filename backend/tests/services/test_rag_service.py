import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.search.rag_service import RagSearchService
from src.models import UserRole
from src.logic import MovieLogic, LibraryLogic, UserAssetLogic, MovieAssetLogic
from src.repos.embedding_repos.note_embedding_repo import NoteEmbeddingRepo
from src.repos.embedding_repos.subtitle_embedding_repo import SubtitleEmbeddingRepo
from src.repos.embedding_repos.movie_embedding_repo import MovieEmbeddingRepo
from src.logic.rag.searcher_logic import HybridSearcher

@pytest.fixture
def mock_service():
    with patch("src.services.search.rag_service.MovieLogic") as MockMovieLogic, \
         patch("src.services.search.rag_service.LibraryLogic") as MockLibraryLogic, \
         patch("src.services.search.rag_service.UserAssetLogic") as MockUserAssetLogic, \
         patch("src.services.search.rag_service.MovieAssetLogic") as MockMovieAssetLogic, \
         patch("src.services.search.rag_service.NoteEmbeddingRepo") as MockNoteRepo, \
         patch("src.services.search.rag_service.SubtitleEmbeddingRepo") as MockSubtitleRepo, \
         patch("src.services.search.rag_service.MovieEmbeddingRepo") as MockMovieRepo, \
         patch("src.services.search.rag_service.HybridSearcher") as MockHybridSearcher, \
         patch("src.services.search.rag_service.get_text_embedding_async", new_callable=AsyncMock) as MockEmbedding:
        
        service = RagSearchService()
        
        # Mock logic instances
        service.movie_logic = MockMovieLogic.return_value
        service.library_logic = MockLibraryLogic.return_value
        service.user_asset_logic = MockUserAssetLogic.return_value
        service.movie_asset_logic = MockMovieAssetLogic.return_value
        
        # Configure async methods on logics
        service.movie_logic.get_movies = AsyncMock(return_value=[])
        service.library_logic.list_libraries = AsyncMock()
        service.library_logic.list_libraries.return_value.items = [] # Default empty libs
        service.user_asset_logic.get_assets = AsyncMock(return_value=[])
        service.movie_asset_logic.get_assets = AsyncMock(return_value=[])
        
        # Mock repos
        service.note_repo = MockNoteRepo.return_value
        service.subtitle_repo = MockSubtitleRepo.return_value
        service.movie_repo = MockMovieRepo.return_value
        
        # Mock searchers
        service.note_searcher = MockHybridSearcher.return_value
        service.subtitle_searcher = MockHybridSearcher.return_value
        service.movie_searcher = MockHybridSearcher.return_value
        
        # Configure search methods
        service.note_searcher.search = AsyncMock(return_value=[])
        service.subtitle_searcher.search = AsyncMock(return_value=[])
        service.movie_searcher.search = AsyncMock(return_value=[])
        
        # Store mock for verification
        service._mock_embedding = MockEmbedding
        
        yield service

@pytest.mark.asyncio
async def test_search_service_init(mock_service):
    assert isinstance(mock_service, RagSearchService)

@pytest.mark.asyncio
async def test_search_basic_flow(mock_service):
    # Setup mocks
    mock_service._mock_embedding.return_value = [[0.1, 0.2]]
    
    # Mock searcher results
    mock_item = MagicMock()
    mock_item.id = "123"
    mock_result = [{"item": mock_item, "score": 0.9}]
    
    mock_service.movie_searcher.search.return_value = mock_result
    
    # Mock resolution
    mock_movie = MagicMock()
    mock_movie.id = "123"
    mock_movie.model_dump.return_value = {"id": "123", "title": "Test Movie"}
    mock_service.movie_logic.get_movies.return_value = [mock_movie]
    
    # Call search
    user = MagicMock()
    user.role = UserRole.USER
    user.id = "user1"
    
    response = await mock_service.search(
        query="test query",
        page=1,
        size=10,
        types=["movies"],
        current_user=user
    )
    
    assert response["status"] == "success"
    assert "movies" in response["data"]
    assert len(response["data"]["movies"]["items"]) == 1
    assert response["data"]["movies"]["items"][0]["movie"]["title"] == "Test Movie"
    
    # Verify searcher called
    mock_service.movie_searcher.search.assert_called_once()
    args, kwargs = mock_service.movie_searcher.search.call_args
    assert kwargs["text"] == "test query"
    assert kwargs["vector"] == [0.1, 0.2]

@pytest.mark.asyncio
async def test_search_with_rewrite(mock_service):
    with patch("src.services.search.rag_service.QueryRewriterFactory") as MockFactory:
        mock_rewriter = AsyncMock()
        mock_rewriter.rewrite.return_value = {
            "original": "bad query",
            "rewritten": "good query",
            "type": "llm"
        }
        MockFactory.create_rewriter.return_value = mock_rewriter
        
        # Use fixture's embedding mock
        mock_service._mock_embedding.return_value = [[0.1]]
        
        user = MagicMock()
        user.role = UserRole.USER
        
        await mock_service.search(
            query="bad query",
            enable_rewrite=True,
            types=["movies"],
            current_user=user
        )
        
        # Verify rewriter used
        MockFactory.create_rewriter.assert_called_with("llm")
        mock_rewriter.rewrite.assert_called_with("bad query")
        
        # Verify search used rewritten query
        mock_service.movie_searcher.search.assert_called()
        args, kwargs = mock_service.movie_searcher.search.call_args
        assert kwargs["text"] == "good query"

@pytest.mark.asyncio
async def test_search_with_rerank(mock_service):
    with patch("src.services.search.rag_service.CrossEncoderReRanker") as MockReranker:
        mock_reranker_instance = MockReranker.return_value
        
        mock_service._mock_embedding.return_value = [[0.1]]
        
        user = MagicMock()
        user.role = UserRole.USER
        
        await mock_service.search(
            query="query",
            enable_rerank=True,
            rerank_type="cross_encoder",
            current_user=user
        )
        
        # Verify search called with reranker
        mock_service.movie_searcher.search.assert_called()
        args, kwargs = mock_service.movie_searcher.search.call_args
        assert kwargs["reranker"] == mock_reranker_instance

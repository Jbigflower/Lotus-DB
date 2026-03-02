import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.search.search_service import SearchService, MovieChunk
from src.models import UserRole
from src.repos.embedding_repos.movie_embedding_repo import MovieEmbeddingRepo
from src.logic import MovieLogic
from src.logic import LibraryLogic
from src.repos.cache_repos.base_redis_repo import BaseRedisRepo

@pytest.mark.asyncio
async def test_search_movies_uses_embedding_repo():
    # Setup mocks
    mock_movie_repo = AsyncMock(spec=MovieEmbeddingRepo)
    mock_movie_logic = AsyncMock(spec=MovieLogic)
    mock_redis_repo = AsyncMock(spec=BaseRedisRepo)
    
    # Mock embedding vector
    embedding_vector = [0.1] * 768
    
    # Mock search result from LanceDB
    chunk1 = MovieChunk(
        id="m1", 
        parent_id="m1", 
        library_id="lib1", 
        title="Test Movie", 
        content="Test Description"
    )
    # search_with_scores returns List[Tuple[Any, Optional[float]]]
    mock_movie_repo.search_with_scores.return_value = [(chunk1, 0.9)]
    
    # Mock movie detail retrieval
    mock_movie = MagicMock()
    mock_movie.id = "m1"
    mock_movie.model_dump.return_value = {"id": "m1", "title": "Test Movie", "library_id": "lib1"}
    mock_movie_logic.get_movies.return_value = [mock_movie]

    # Initialize service with mocks
    with patch("src.services.search.search_service.MovieEmbeddingRepo", return_value=mock_movie_repo), \
         patch("src.services.search.search_service.MovieLogic", return_value=mock_movie_logic), \
         patch("src.services.search.search_service.BaseRedisRepo", return_value=mock_redis_repo), \
         patch("src.services.search.search_service.get_text_embedding_async", new_callable=AsyncMock) as mock_get_embedding:
        
        mock_get_embedding.return_value = [embedding_vector]
        mock_redis_repo.get.return_value = None  # Cache miss
        
        service = SearchService()
        # Ensure mocks are used (__init__ might have created new instances if patch wasn't active during import, 
        # but patch here mocks the class constructor, so service.movie_embedding_repo should be our mock)
        
        # Verify service has our mocks
        assert service.movie_embedding_repo == mock_movie_repo
        assert service.movie_logic == mock_movie_logic
        
        # Execute search
        result = await service.ns_search(
            query="test query",
            types=["movies"], # request only movies
            page=1,
            size=10,
            current_user=MagicMock(role=UserRole.ADMIN, id="admin")
        )
        
        # Verify embedding was generated
        mock_get_embedding.assert_called_once()
        
        # Verify repo search was called
        mock_movie_repo.search_with_scores.assert_called_once()
        call_args = mock_movie_repo.search_with_scores.call_args
        assert call_args[0][0] == embedding_vector # 1st arg: embedding
        
        # Verify results structure
        # ns_search returns {status, query, data: {movies: ...}, meta: ...}
        assert result["data"]["movies"]["items"][0]["chunk"]["id"] == "m1"
        assert result["data"]["movies"]["items"][0]["movie"]["title"] == "Test Movie"
        # Score is recalculated by ranker, so just check it exists
        assert "score" in result["data"]["movies"]["items"][0]

@pytest.mark.asyncio
async def test_search_movies_filters_non_admin():
    # Setup mocks
    mock_movie_repo = AsyncMock(spec=MovieEmbeddingRepo)
    mock_movie_logic = AsyncMock(spec=MovieLogic)
    mock_lib_logic = AsyncMock()
    mock_redis_repo = AsyncMock(spec=BaseRedisRepo)
    
    # Mock library access
    mock_lib_page = MagicMock()
    mock_lib1 = MagicMock()
    mock_lib1.id = "lib1"
    mock_lib2 = MagicMock()
    mock_lib2.id = "lib2"
    mock_lib_page.items = [mock_lib1, mock_lib2]
    mock_lib_logic.list_libraries.return_value = mock_lib_page
    
    with patch("src.services.search.search_service.MovieEmbeddingRepo", return_value=mock_movie_repo), \
         patch("src.services.search.search_service.MovieLogic", return_value=mock_movie_logic), \
         patch("src.services.search.search_service.LibraryLogic", return_value=mock_lib_logic), \
         patch("src.services.search.search_service.BaseRedisRepo", return_value=mock_redis_repo), \
         patch("src.services.search.search_service.get_text_embedding_async", new_callable=AsyncMock) as mock_get_embedding:
        
        mock_get_embedding.return_value = [[0.1] * 768]
        mock_movie_repo.search_with_scores.return_value = []
        mock_redis_repo.get.return_value = None  # Cache miss
        
        service = SearchService()
        
        # Execute search as user
        await service.ns_search(
            query="test",
            types=["movies"],
            page=1,
            size=10,
            current_user=MagicMock(role=UserRole.USER, id="u1")
        )
        
        # Verify filters passed to repo
        mock_movie_repo.search_with_scores.assert_called_once()
        _, kwargs = mock_movie_repo.search_with_scores.call_args
        assert "filters" in kwargs
        assert kwargs["filters"]["library_id"] == ["lib1", "lib2"]

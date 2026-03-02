from src.services.search.search_service import SearchService
from src.repos.embedding_repos.note_embedding_repo import NoteChunk


def test_rewrite_query_tokens():
    service = SearchService.__new__(SearchService)
    result = service._rewrite_query("  机器 学习 ")
    assert result["normalized"] == "机器 学习"
    assert "机器" in result["tokens"]
    assert "学习" in result["tokens"]


def test_keyword_score():
    service = SearchService.__new__(SearchService)
    score = service._keyword_score("深度学习", ["深度", "学习"])
    assert score == 1.0


def test_rank_chunks_max_per_parent():
    service = SearchService.__new__(SearchService)
    chunks = [
        (
            NoteChunk(
                id="a1",
                parent_id="p1",
                chunk_index=0,
                user_id="u1",
                movie_id="m1",
                is_public=True,
                content="测试 内容",
            ),
            0.1,
        ),
        (
            NoteChunk(
                id="a2",
                parent_id="p1",
                chunk_index=1,
                user_id="u1",
                movie_id="m1",
                is_public=True,
                content="测试 其他",
            ),
            0.2,
        ),
        (
            NoteChunk(
                id="b1",
                parent_id="p2",
                chunk_index=0,
                user_id="u1",
                movie_id="m2",
                is_public=True,
                content="测试 其它",
            ),
            0.3,
        ),
    ]
    ranked = service._rank_chunks(
        chunks, ["测试"], 0.7, 0.3, max_per_parent=1, parent_attr="parent_id"
    )
    parent_ids = [item["chunk"].parent_id for item in ranked]
    assert parent_ids.count("p1") == 1

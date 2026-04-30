"""
Unit tests for retrieval_service.

All OpenAI and Qdrant calls are patched. We test:
  - top_k is forwarded correctly to Qdrant
  - score threshold filters out low-confidence results
  - document_id filter is constructed and passed
  - empty Qdrant results produce a warning and empty chunks
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.retrieval_service import (
    DEFAULT_SCORE_THRESHOLD,
    _build_filter,
    retrieve_relevant_chunks,
    retrieve_with_filter,
)
from tests.conftest import (
    make_openai_embedding,
    make_qdrant_point,
    make_query_response,
)

# ---------------------------------------------------------------------------
# _build_filter — pure function
# ---------------------------------------------------------------------------


def test_build_filter_returns_none_when_no_ids():
    assert _build_filter(None) is None
    assert _build_filter([]) is None


def test_build_filter_returns_filter_for_ids():
    from qdrant_client.models import Filter

    result = _build_filter(["doc-1", "doc-2"])
    assert isinstance(result, Filter)
    assert result.must[0].key == "document_id"
    assert result.must[0].match.any == ["doc-1", "doc-2"]


# ---------------------------------------------------------------------------
# retrieve_relevant_chunks
# ---------------------------------------------------------------------------


def _patch_retrieval(points: list, embedding: list[float] | None = None):
    """Context manager that patches OpenAI + Qdrant for retrieval tests."""
    if embedding is None:
        embedding = make_openai_embedding()

    embed_resp = MagicMock()
    embed_resp.data = [MagicMock(embedding=embedding)]

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=embed_resp)

    mock_qdrant = AsyncMock()
    mock_qdrant.query_points = AsyncMock(return_value=make_query_response(points))
    mock_qdrant.close = AsyncMock()

    return (
        patch("app.services.retrieval_service.AsyncOpenAI", return_value=mock_openai),
        patch("app.services.retrieval_service.AsyncQdrantClient", return_value=mock_qdrant),
        mock_qdrant,
    )


@pytest.mark.asyncio
async def test_top_k_forwarded_to_qdrant():
    """The top_k argument must be passed as `limit` to qdrant.query_points."""
    points = [make_qdrant_point(score=0.9)]
    patch_openai, patch_qdrant, mock_qdrant = _patch_retrieval(points)

    with patch_openai, patch_qdrant:
        chunks, _ = await retrieve_relevant_chunks("What is revenue?", top_k=3)

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    assert call_kwargs["limit"] == 3


@pytest.mark.asyncio
async def test_score_threshold_filters_low_scoring_results():
    """Results below the threshold must be excluded and a warning returned."""
    low_score_point = make_qdrant_point(score=0.40)
    patch_openai, patch_qdrant, _ = _patch_retrieval([low_score_point])

    with patch_openai, patch_qdrant:
        chunks, warning = await retrieve_relevant_chunks(
            "What is revenue?", score_threshold=DEFAULT_SCORE_THRESHOLD
        )

    assert chunks == []
    assert warning is not None
    assert "0.400" in warning  # top score appears in the warning message


@pytest.mark.asyncio
async def test_high_scoring_results_returned_as_chunks():
    """Results at or above the threshold are returned as RetrievedChunk objects."""
    high_score_point = make_qdrant_point(score=0.85, text="Revenue was $25B.")
    patch_openai, patch_qdrant, _ = _patch_retrieval([high_score_point])

    with patch_openai, patch_qdrant:
        chunks, warning = await retrieve_relevant_chunks("What is revenue?")

    assert len(chunks) == 1
    assert chunks[0].score == 0.85
    assert chunks[0].text == "Revenue was $25B."
    assert warning is None


@pytest.mark.asyncio
async def test_document_ids_filter_passed_to_qdrant():
    """retrieve_with_filter must construct a Qdrant filter from the document_ids."""
    points = [make_qdrant_point(score=0.9, document_id="doc-xyz")]
    patch_openai, patch_qdrant, mock_qdrant = _patch_retrieval(points)

    with patch_openai, patch_qdrant:
        chunks, _ = await retrieve_with_filter("What is revenue?", document_ids=["doc-xyz"])

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    query_filter = call_kwargs.get("query_filter")
    assert query_filter is not None
    assert query_filter.must[0].match.any == ["doc-xyz"]


@pytest.mark.asyncio
async def test_empty_qdrant_results_return_warning():
    """No Qdrant results → empty chunk list + non-None warning."""
    patch_openai, patch_qdrant, _ = _patch_retrieval([])

    with patch_openai, patch_qdrant:
        chunks, warning = await retrieve_relevant_chunks("Any question")

    assert chunks == []
    assert warning is not None

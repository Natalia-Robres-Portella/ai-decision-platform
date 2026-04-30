"""
Unit tests for qa_service.

All OpenAI calls and retrieval calls are patched. We test:
  - AnswerResponse contains sources when chunks are found
  - confidence maps correctly from top score
  - LLM is NOT called when retrieval returns no chunks (cost guard)
  - token count from OpenAI completion is passed through to the response
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.retrieval import RetrievedChunk
from app.services.qa_service import _determine_confidence, answer_question
from tests.conftest import make_chat_completion

# ---------------------------------------------------------------------------
# _determine_confidence — pure function
# ---------------------------------------------------------------------------


def test_confidence_high_above_threshold():
    assert _determine_confidence(0.81) == "high"
    assert _determine_confidence(1.0) == "high"


def test_confidence_medium_in_range():
    assert _determine_confidence(0.75) == "medium"
    assert _determine_confidence(0.60) == "medium"


def test_confidence_low_below_threshold():
    assert _determine_confidence(0.59) == "low"
    assert _determine_confidence(0.0) == "low"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(score: float = 0.85, text: str = "Revenue was $25B.") -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        score=score,
        document_id="doc-001",
        filename="tesla.pdf",
        page_number=3,
        chunk_index=0,
    )


# ---------------------------------------------------------------------------
# answer_question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_includes_sources_from_retrieved_chunks(db_session):
    """AnswerResponse.sources must contain one entry per retrieved chunk."""
    chunks = [_make_chunk(score=0.85), _make_chunk(score=0.75, text="Q3 net income.")]
    completion = make_chat_completion(content="Tesla revenue grew significantly.", total_tokens=80)

    with (
        patch(
            "app.services.qa_service.retrieve_relevant_chunks",
            return_value=(chunks, None),
        ),
        patch("app.services.qa_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)
        mock_openai_cls.return_value = mock_client

        response = await answer_question(
            question="What is Tesla revenue?",
            document_ids=None,
            db=db_session,
        )

    assert len(response.sources) == 2
    assert response.sources[0].filename == "tesla.pdf"
    assert response.sources[0].page_number == 3


@pytest.mark.asyncio
async def test_confidence_high_when_top_score_exceeds_0_80(db_session):
    """Confidence must be 'high' when the top chunk score is > 0.80."""
    chunks = [_make_chunk(score=0.90)]
    completion = make_chat_completion()

    with (
        patch(
            "app.services.qa_service.retrieve_relevant_chunks",
            return_value=(chunks, None),
        ),
        patch("app.services.qa_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)
        mock_openai_cls.return_value = mock_client

        response = await answer_question("Revenue?", document_ids=None, db=db_session)

    assert response.confidence == "high"


@pytest.mark.asyncio
async def test_llm_not_called_when_no_chunks_returned(db_session):
    """When retrieval returns no chunks, the LLM must not be invoked (saves API cost)."""
    with (
        patch(
            "app.services.qa_service.retrieve_relevant_chunks",
            return_value=([], "no content found"),
        ),
        patch("app.services.qa_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        response = await answer_question(
            "Random unrelated question", document_ids=None, db=db_session
        )

    mock_client.chat.completions.create.assert_not_called()
    assert response.tokens_used == 0
    assert response.confidence == "low"
    assert response.sources == []


@pytest.mark.asyncio
async def test_token_count_from_completion_is_passed_through(db_session):
    """tokens_used in the response must match what OpenAI reports in completion.usage."""
    chunks = [_make_chunk(score=0.82)]
    completion = make_chat_completion(total_tokens=237)

    with (
        patch(
            "app.services.qa_service.retrieve_relevant_chunks",
            return_value=(chunks, None),
        ),
        patch("app.services.qa_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)
        mock_openai_cls.return_value = mock_client

        response = await answer_question("Revenue?", document_ids=None, db=db_session)

    assert response.tokens_used == 237


@pytest.mark.asyncio
async def test_answer_uses_document_ids_filter_when_provided(db_session):
    """When document_ids are passed, retrieve_with_filter must be called instead of retrieve_relevant_chunks."""
    chunks = [_make_chunk(score=0.88)]
    completion = make_chat_completion()

    with (
        patch(
            "app.services.qa_service.retrieve_with_filter", return_value=(chunks, None)
        ) as mock_filter,
        patch("app.services.qa_service.retrieve_relevant_chunks") as mock_global,
        patch("app.services.qa_service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=completion)
        mock_openai_cls.return_value = mock_client

        await answer_question("Revenue?", document_ids=["doc-1"], db=db_session)

    mock_filter.assert_called_once()
    mock_global.assert_not_called()

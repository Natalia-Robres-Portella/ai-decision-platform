"""
Integration tests that exercise the full HTTP stack.

Each test sends a real HTTP request through the FastAPI app (via httpx ASGI
transport). External I/O (OpenAI, Qdrant) is patched at the module level so
no running services are required.

The `client` fixture (from conftest) handles:
  - SQLite in-memory replacing Postgres
  - Qdrant lifespan stubbed out
  - FastAPI DI override for get_db
"""

import io
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import (
    make_chat_completion,
    make_minimal_pdf_bytes,
    make_openai_embedding_response,
    make_qdrant_point,
    make_query_response,
)

# ---------------------------------------------------------------------------
# /api/v1/ask (non-streaming)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_returns_answer_and_sources(client):
    """POST /ask must return a JSON body with answer text and at least one source."""
    point = make_qdrant_point(score=0.88, text="Tesla Q4 revenue was $25.2 billion.")
    embed_resp = make_openai_embedding_response()
    completion = make_chat_completion("Tesla's Q4 revenue was $25.2 billion.")

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=embed_resp)
    mock_openai.chat.completions.create = AsyncMock(return_value=completion)

    mock_qdrant = AsyncMock()
    mock_qdrant.query_points = AsyncMock(return_value=make_query_response([point]))
    mock_qdrant.close = AsyncMock()

    with (
        patch("app.services.retrieval_service.AsyncOpenAI", return_value=mock_openai),
        patch("app.services.retrieval_service.AsyncQdrantClient", return_value=mock_qdrant),
        patch("app.services.qa_service.AsyncOpenAI", return_value=mock_openai),
    ):
        response = await client.post(
            "/api/v1/ask", json={"question": "What is Tesla's Q4 revenue?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert "answer" in body
    assert len(body["answer"]) > 0
    assert "sources" in body
    assert len(body["sources"]) >= 1
    assert body["sources"][0]["filename"] == "tesla.pdf"


@pytest.mark.asyncio
async def test_ask_graceful_decline_when_no_relevant_chunks(client):
    """POST /ask must return a helpful message (not 500) when retrieval finds nothing."""
    embed_resp = make_openai_embedding_response()

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=embed_resp)

    mock_qdrant = AsyncMock()
    mock_qdrant.query_points = AsyncMock(return_value=make_query_response([]))
    mock_qdrant.close = AsyncMock()

    with (
        patch("app.services.retrieval_service.AsyncOpenAI", return_value=mock_openai),
        patch("app.services.retrieval_service.AsyncQdrantClient", return_value=mock_qdrant),
        patch("app.services.qa_service.AsyncOpenAI", return_value=mock_openai),
    ):
        response = await client.post(
            "/api/v1/ask", json={"question": "What is the population of Mars?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == "low"
    assert body["tokens_used"] == 0
    assert body["sources"] == []


# ---------------------------------------------------------------------------
# /api/v1/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_returns_list(client):
    """GET /history must return a JSON array (empty is valid on a fresh DB)."""
    response = await client.get("/api/v1/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_history_records_interaction_after_ask(client):
    """After a successful /ask, /history must contain the question."""
    point = make_qdrant_point(score=0.88, text="Operating margin was 15%.")
    embed_resp = make_openai_embedding_response()
    completion = make_chat_completion("Operating margin was 15%.", total_tokens=60)

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=embed_resp)
    mock_openai.chat.completions.create = AsyncMock(return_value=completion)

    mock_qdrant = AsyncMock()
    mock_qdrant.query_points = AsyncMock(return_value=make_query_response([point]))
    mock_qdrant.close = AsyncMock()

    with (
        patch("app.services.retrieval_service.AsyncOpenAI", return_value=mock_openai),
        patch("app.services.retrieval_service.AsyncQdrantClient", return_value=mock_qdrant),
        patch("app.services.qa_service.AsyncOpenAI", return_value=mock_openai),
    ):
        ask_response = await client.post(
            "/api/v1/ask", json={"question": "What is the operating margin?"}
        )

    assert ask_response.status_code == 200

    history_response = await client.get("/api/v1/history")
    assert history_response.status_code == 200
    history = history_response.json()

    assert len(history) >= 1
    questions = [entry["question"] for entry in history]
    assert "What is the operating margin?" in questions


# ---------------------------------------------------------------------------
# /api/v1/ingest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_endpoint_returns_document_id(client):
    """POST /ingest must respond with a document_id string and status=processing."""
    pdf_bytes = make_minimal_pdf_bytes()

    embed_resp = make_openai_embedding_response()
    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=embed_resp)

    mock_qdrant = AsyncMock()
    mock_qdrant.upsert = AsyncMock()
    mock_qdrant.close = AsyncMock()

    with (
        patch("app.services.ingestion_service.AsyncOpenAI", return_value=mock_openai),
        patch("app.services.ingestion_service.AsyncQdrantClient", return_value=mock_qdrant),
    ):
        response = await client.post(
            "/api/v1/documents/ingest",
            files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )

    assert response.status_code == 201
    body = response.json()
    assert "document_id" in body
    assert len(body["document_id"]) > 0

"""
Unit tests for ingestion_service.

These tests isolate each function — no real PDFs, no Qdrant, no OpenAI.
External I/O is patched at the boundary where it enters the module.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ingestion_service import (
    _TOKENIZER,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    chunk_document,
    embed_and_store,
    load_pdf,
)
from tests.conftest import make_minimal_pdf_bytes, make_openai_embedding_response

# ---------------------------------------------------------------------------
# chunk_document — pure function, no mocking needed
# ---------------------------------------------------------------------------


def test_chunk_max_size_never_exceeded():
    """No chunk should contain more than CHUNK_SIZE tokens.

    This is the core invariant of the chunking function: we guarantee the
    embedding model never receives a sequence longer than CHUNK_SIZE tokens.
    Violating it would silently truncate content at the embedding layer.
    """
    long_text = "The quick brown fox jumps over the lazy dog. " * 200
    chunks = chunk_document(long_text)

    assert len(chunks) > 1, "long text should produce multiple chunks"
    for chunk in chunks:
        token_count = len(_TOKENIZER.encode(chunk))
        assert token_count <= CHUNK_SIZE, (
            f"chunk has {token_count} tokens, exceeds CHUNK_SIZE={CHUNK_SIZE}"
        )


def test_chunk_overlap_tokens_shared_between_consecutive_chunks():
    """The tail of chunk[n] should overlap with the head of chunk[n+1].

    Overlap ensures boundary sentences are preserved in at least one complete
    chunk. We verify it at the token level — the shared token count must equal
    CHUNK_OVERLAP (or fewer, if the last window is smaller than CHUNK_SIZE).
    """
    # Enough text to produce at least 3 chunks
    text = "word " * (CHUNK_SIZE * 3)
    chunks = chunk_document(text)

    assert len(chunks) >= 2

    tokens_0 = _TOKENIZER.encode(chunks[0])
    tokens_1 = _TOKENIZER.encode(chunks[1])

    # The tail of chunk 0 should match the head of chunk 1
    shared = tokens_0[-CHUNK_OVERLAP:]
    head = tokens_1[:CHUNK_OVERLAP]
    assert shared == head, "overlapping tokens must be identical across chunk boundary"


def test_chunk_empty_string_returns_empty_list():
    """Empty input must produce an empty chunk list, not a list with one empty string."""
    assert chunk_document("") == []


def test_chunk_short_text_returns_single_chunk():
    """Text shorter than CHUNK_SIZE should not be split."""
    text = "Short text."
    chunks = chunk_document(text)
    assert len(chunks) == 1
    assert chunks[0] == text


# ---------------------------------------------------------------------------
# load_pdf — tests file extension validation
# ---------------------------------------------------------------------------


def test_load_pdf_raises_for_non_pdf():
    """load_pdf must reject non-PDF files before attempting to parse them."""
    with pytest.raises(ValueError, match="Only PDF files are accepted"):
        load_pdf("report.docx")


def test_load_pdf_raises_for_txt():
    with pytest.raises(ValueError, match="Only PDF files are accepted"):
        load_pdf("data.txt")


def test_load_pdf_returns_page_dicts(tmp_path):
    """load_pdf should return a list of {page_number, text} dicts for a valid PDF."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(make_minimal_pdf_bytes())

    pages = load_pdf(str(pdf_path))

    assert isinstance(pages, list)
    assert len(pages) >= 1
    for page in pages:
        assert "page_number" in page
        assert "text" in page
        assert isinstance(page["page_number"], int)
        assert isinstance(page["text"], str)


# ---------------------------------------------------------------------------
# embed_and_store — patches OpenAI + Qdrant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_and_store_sends_correct_metadata():
    """embed_and_store must include filename, document_id, and page_number in every Qdrant point payload."""
    chunks = [
        {"text": "Revenue grew 12%.", "page_number": 1, "chunk_index": 0},
        {"text": "Operating margin improved.", "page_number": 2, "chunk_index": 1},
    ]
    document_id = "doc-abc"
    metadata = {"filename": "report.pdf", "source_type": "pdf"}

    mock_embed_resp = make_openai_embedding_response()
    mock_embed_resp.data = [
        mock_embed_resp.data[0],
        mock_embed_resp.data[0],
    ]  # 2 embeddings

    mock_openai = AsyncMock()
    mock_openai.embeddings.create = AsyncMock(return_value=mock_embed_resp)

    mock_qdrant = AsyncMock()
    mock_qdrant.upsert = AsyncMock()
    mock_qdrant.close = AsyncMock()

    with (
        patch("app.services.ingestion_service.AsyncOpenAI", return_value=mock_openai),
        patch("app.services.ingestion_service.AsyncQdrantClient", return_value=mock_qdrant),
    ):
        await embed_and_store(chunks, document_id, metadata)

    # Qdrant upsert was called
    assert mock_qdrant.upsert.called

    upsert_call = mock_qdrant.upsert.call_args
    points = (
        upsert_call.kwargs.get("points") or upsert_call.args[1]
        if upsert_call.args
        else upsert_call.kwargs["points"]
    )

    assert len(points) == 2
    for i, point in enumerate(points):
        assert point.payload["document_id"] == document_id
        assert point.payload["filename"] == "report.pdf"
        assert point.payload["page_number"] == chunks[i]["page_number"]
        assert point.payload["text"] == chunks[i]["text"]

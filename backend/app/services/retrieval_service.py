"""
Retrieval layer: embed a query → search Qdrant → return ranked chunks.

This is the R in RAG. The output feeds directly into the LLM prompt
in the next step (generation).
"""

import time

import structlog
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

from app.config import settings
from app.schemas.retrieval import RetrievedChunk

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Two-tier threshold system:
#
# Cosine similarity for text-embedding-3-small in practice:
#   < 0.25  → completely unrelated (different topic entirely) → reject
#   0.25–0.45 → weak overlap → fallback zone: pass to LLM with caveat
#   0.45–0.70 → relevant content (normal RAG zone)            ← target
#   0.70–0.85 → highly relevant, similar phrasing
#   > 0.85  → near-identical or paraphrased text
#
# DEFAULT_SCORE_THRESHOLD: chunks above this are "good" context.
# FALLBACK_SCORE_THRESHOLD: if no good chunk found but best score is above
#   this floor, return chunks anyway with is_low_confidence=True so the LLM
#   knows to hedge. Prevents "No relevant content" on valid but weakly-matched
#   queries (e.g. Spanish query vs. English document).
#
# How to tune:
#   Hallucinated answers → raise DEFAULT to 0.50–0.55
#   Still too many "no content" → lower FALLBACK to 0.20
#   Very technical domain → raise DEFAULT to 0.60+
# ---------------------------------------------------------------------------
DEFAULT_SCORE_THRESHOLD = 0.45
FALLBACK_SCORE_THRESHOLD = 0.25


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _embed_query(query: str) -> list[float]:
    """Embed a single query string.

    Uses the same model as ingestion (text-embedding-3-small) so the vectors
    live in the same semantic space. Mixing embedding models would produce
    meaningless similarity scores.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model="text-embedding-3-small",
        input=query,
    )
    return response.data[0].embedding


def _build_filter(document_ids: list[str] | None) -> Filter | None:
    """Build a Qdrant payload filter to restrict search to specific documents.

    MatchAny is the Qdrant equivalent of SQL's WHERE document_id IN (...).
    This runs server-side before the ANN (approximate nearest-neighbour) search,
    so it's efficient — Qdrant doesn't scan filtered-out points.
    """
    if not document_ids:
        return None
    return Filter(must=[FieldCondition(key="document_id", match=MatchAny(any=document_ids))])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def retrieve_relevant_chunks(
    query: str,
    top_k: int = 5,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> tuple[list[RetrievedChunk], str | None, bool]:
    """Embed query and return the top_k most semantically similar chunks.

    Returns (chunks, warning, is_low_confidence).
    is_low_confidence=True when chunks were returned via the fallback tier
    (score between FALLBACK_SCORE_THRESHOLD and score_threshold).
    """
    return await _retrieve(query, top_k, score_threshold, document_ids=None)


async def retrieve_with_filter(
    query: str,
    top_k: int = 5,
    document_ids: list[str] | None = None,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> tuple[list[RetrievedChunk], str | None, bool]:
    """Same as retrieve_relevant_chunks, scoped to specific document IDs."""
    return await _retrieve(query, top_k, score_threshold, document_ids=document_ids)


# ---------------------------------------------------------------------------
# Core retrieval logic
# ---------------------------------------------------------------------------


async def _retrieve(
    query: str,
    top_k: int,
    score_threshold: float,
    document_ids: list[str] | None,
) -> tuple[list[RetrievedChunk], str | None, bool]:
    start = time.perf_counter()

    query_vector = await _embed_query(query)

    qdrant = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    try:
        # qdrant-client 1.7+ replaced .search() with .query_points().
        # The response is a QueryResponse; the matches are in .points.
        response = await qdrant.query_points(
            collection_name=settings.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=_build_filter(document_ids),
            with_payload=True,
            # We intentionally do NOT pass score_threshold to Qdrant here.
            # We want to see the top score even when it's below our threshold,
            # so we can log it and return a useful warning to the caller.
        )
        results = response.points
    finally:
        await qdrant.close()

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    top_score = results[0].score if results else 0.0

    # --- Two-tier threshold ---
    # Tier 1 (score >= score_threshold): high-confidence match → normal answer.
    # Tier 2 (FALLBACK_SCORE_THRESHOLD <= score < score_threshold): weak match
    #   → return chunks but flag is_low_confidence=True so the LLM hedges.
    # Below FALLBACK_SCORE_THRESHOLD: truly unrelated → reject with warning.
    warning: str | None = None
    is_low_confidence = False

    if not results or top_score < FALLBACK_SCORE_THRESHOLD:
        warning = (
            f"No relevant content found (best score: {top_score:.3f}, "
            f"threshold: {score_threshold}). "
            "Try rephrasing your query or uploading documents on this topic."
        )
        chunks: list[RetrievedChunk] = []
    elif top_score < score_threshold:
        # Fallback tier: best match is weak but above the noise floor.
        is_low_confidence = True
        warning = (
            f"Low-confidence match (best score: {top_score:.3f}). "
            "Answer may not be fully grounded in the documents."
        )
        chunks = [
            RetrievedChunk(
                text=r.payload["text"],
                score=round(r.score, 4),
                document_id=r.payload["document_id"],
                filename=r.payload["filename"],
                page_number=r.payload["page_number"],
                chunk_index=r.payload["chunk_index"],
            )
            for r in results
            if r.score >= FALLBACK_SCORE_THRESHOLD
        ]
    else:
        chunks = [
            RetrievedChunk(
                text=r.payload["text"],
                score=round(r.score, 4),
                document_id=r.payload["document_id"],
                filename=r.payload["filename"],
                page_number=r.payload["page_number"],
                chunk_index=r.payload["chunk_index"],
            )
            for r in results
            if r.score >= score_threshold
        ]

    logger.info(
        "retrieval.completed",
        query=query[:120],  # truncate long queries for log readability
        num_results=len(chunks),
        top_score=round(top_score, 4),
        score_threshold=score_threshold,
        fallback_threshold=FALLBACK_SCORE_THRESHOLD,
        is_low_confidence=is_low_confidence,
        document_filter=document_ids,
        latency_ms=latency_ms,
    )

    return chunks, warning, is_low_confidence

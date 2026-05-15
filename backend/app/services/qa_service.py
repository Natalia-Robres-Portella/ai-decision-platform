"""
Generation layer: retrieval → prompt → LLM → structured answer.

This is the G in RAG. It orchestrates retrieval_service and wraps the
LLM call with prompt engineering that keeps answers grounded in sources.
"""

import json
from typing import AsyncGenerator, Literal

import structlog
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.repositories.history_repository import HistoryRepository
from app.schemas.answer import AnswerResponse, SourceReference
from app.schemas.retrieval import RetrievedChunk
from app.services.retrieval_service import (
    retrieve_relevant_chunks,
    retrieve_with_filter,
)

logger = structlog.get_logger()

MODEL = "gpt-4o-mini"
EXCERPT_LENGTH = 200

# ---------------------------------------------------------------------------
# Prompt engineering
#
# Every word here is load-bearing. Here's why each instruction exists:
#
# "Answer based ONLY on the provided context"
#   LLMs default to blending retrieved context with their training knowledge.
#   For financial documents, training data may be from a different quarter or
#   company. "ONLY" forces the model to treat the context as its sole source
#   of truth, preventing silent knowledge contamination.
#
# "If the context doesn't contain sufficient information, say so explicitly"
#   Without this, the model will try to answer anyway — that's its default
#   bias. Giving it explicit permission to decline produces "I don't know"
#   instead of a confident hallucination.
#
# "Always cite sources as: (Source: {filename}, page {N})"
#   The format hint is critical. Vague citation instructions like "cite your
#   sources" produce "according to the document..." with no actionable
#   reference. The explicit format produces traceable citations the UI can
#   hyperlink to the original PDF page.
#
# Why temperature=0.2 and not 0.0?
#   0.0 = greedy decoding: always picks the single most probable token.
#         Maximally consistent but robotic; bad at prose variation.
#   0.2 = slight stochasticity: the model can rephrase "$25.2B revenue"
#         naturally while remaining factually conservative. It won't invent
#         numbers or elaborate beyond the source text.
#   0.7+ = starts embellishing. At high temperature, the model "rounds"
#          numbers, conflates quarters, and fills gaps with plausible-sounding
#          fabrications. Never use this for financial documents.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a strategic business analyst assistant. "
    "Answer questions based ONLY on the provided context — never use outside knowledge. "
    "If the context does not contain sufficient information, say so explicitly. "
    "Always cite sources in the format: (Source: {filename}, page {N})."
)

LOW_CONFIDENCE_SYSTEM_PROMPT = (
    "You are a strategic business analyst assistant. "
    "The context below is a weak semantic match for the question — it may only partially cover the topic. "
    "Answer based on what IS in the context. "
    "If the context is insufficient, say so explicitly and explain what information is missing. "
    "Never invent data. Always cite sources in the format: (Source: {filename}, page {N})."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _determine_confidence(top_score: float) -> Literal["high", "medium", "low"]:
    if top_score > 0.80:
        return "high"
    elif top_score >= 0.60:
        return "medium"
    else:
        return "low"


def _build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a source-tagged context block.

    The [Source: ...] tag before each chunk is the key prompt engineering move:
    it trains the model's attention to associate each passage with its exact
    origin, so when it writes "(Source: tesla.pdf, page 3)" in the answer
    that citation is accurate — it comes from the tag we injected, not from
    a guess. Without these tags, citations are vague or fabricated.

    The --- separator between chunks prevents the model from blending two
    adjacent passages into a single "source" when citing.
    """
    parts = [f"[Source: {c.filename}, Page {c.page_number}]\n{c.text}" for c in chunks]
    return "\n\n---\n\n".join(parts)


def _build_sources(chunks: list[RetrievedChunk]) -> list[SourceReference]:
    return [
        SourceReference(
            filename=c.filename,
            page_number=c.page_number,
            relevance_score=c.score,
            excerpt=c.text[:EXCERPT_LENGTH] + "…" if len(c.text) > EXCERPT_LENGTH else c.text,
        )
        for c in chunks
    ]


def _no_context_answer(warning: str | None) -> str:
    return (
        "The provided documents do not contain sufficient information to answer this question. "
        + (warning or "Try uploading relevant documents or rephrasing your query.")
    )


# ---------------------------------------------------------------------------
# Standard (non-streaming) answer
# ---------------------------------------------------------------------------


async def answer_question(
    question: str,
    document_ids: list[str] | None,
    db: AsyncSession,
) -> AnswerResponse:
    # 1. Retrieve
    if document_ids:
        chunks, warning, is_low_confidence = await retrieve_with_filter(question, top_k=5, document_ids=document_ids)
    else:
        chunks, warning, is_low_confidence = await retrieve_relevant_chunks(question, top_k=5)

    # 2. No context → graceful decline
    if not chunks:
        answer_text = _no_context_answer(warning)
        repo = HistoryRepository(db)
        await repo.save_interaction(question, answer_text, "low", 0, [])
        return AnswerResponse(
            query=question,
            answer=answer_text,
            sources=[],
            confidence="low",
            model_used=MODEL,
            tokens_used=0,
        )

    # 3. Build prompt — use a hedging system prompt for weak matches
    context = _build_context_block(chunks)
    system_prompt = LOW_CONFIDENCE_SYSTEM_PROMPT if is_low_confidence else SYSTEM_PROMPT
    user_message = f"Context:\n\n{context}\n\nQuestion: {question}"

    # 4. Call LLM
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    completion = await client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    answer_text = completion.choices[0].message.content or ""
    tokens_used = completion.usage.total_tokens if completion.usage else 0
    confidence = _determine_confidence(chunks[0].score)
    sources = _build_sources(chunks)

    # 5. Persist interaction
    repo = HistoryRepository(db)
    await repo.save_interaction(
        question,
        answer_text,
        confidence,
        tokens_used,
        [s.model_dump() for s in sources],
    )

    logger.info(
        "qa.answered",
        question=question[:100],
        confidence=confidence,
        top_score=chunks[0].score,
        tokens_used=tokens_used,
        model=MODEL,
    )

    return AnswerResponse(
        query=question,
        answer=answer_text,
        sources=sources,
        confidence=confidence,
        model_used=MODEL,
        tokens_used=tokens_used,
    )


# ---------------------------------------------------------------------------
# Streaming answer (SSE)
# ---------------------------------------------------------------------------


async def stream_answer_tokens(
    question: str,
    document_ids: list[str] | None,
    state: dict,  # mutable container; populated at end for background history save
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE-formatted lines.

    SSE event types:
      {"type": "token",   "content": "..."}  — one LLM output token
      {"type": "sources", "content": [...]}  — source list after stream ends
      {"type": "error",   "content": "..."}  — retrieval failed
      "data: [DONE]"                         — signals client the stream is finished

    Why SSE and not WebSockets?
    SSE is unidirectional (server → client), which is all we need for streaming
    text. It works over plain HTTP/1.1, requires no handshake, and reconnects
    automatically on drop. WebSockets add bidirectional complexity we don't need.
    """
    if document_ids:
        chunks, warning, is_low_confidence = await retrieve_with_filter(question, top_k=5, document_ids=document_ids)
    else:
        chunks, warning, is_low_confidence = await retrieve_relevant_chunks(question, top_k=5)

    if not chunks:
        yield f"data: {json.dumps({'type': 'error', 'content': warning or 'No relevant content found'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    context = _build_context_block(chunks)
    sources = _build_sources(chunks)
    system_prompt = LOW_CONFIDENCE_SYSTEM_PROMPT if is_low_confidence else SYSTEM_PROMPT
    user_message = f"Context:\n\n{context}\n\nQuestion: {question}"

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    stream = await client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        stream=True,
        stream_options={"include_usage": True},  # usage arrives in the final chunk
    )

    full_answer: list[str] = []
    total_tokens = 0

    async for chunk in stream:
        # The final chunk carries usage data and has empty choices
        if chunk.usage:
            total_tokens = chunk.usage.total_tokens

        if not chunk.choices:
            continue

        delta_content = chunk.choices[0].delta.content
        if delta_content:
            full_answer.append(delta_content)
            yield f"data: {json.dumps({'type': 'token', 'content': delta_content})}\n\n"

    # Sources sent as a single structured event after the last token
    yield f"data: {json.dumps({'type': 'sources', 'content': [s.model_dump() for s in sources]})}\n\n"
    yield "data: [DONE]\n\n"

    # Populate state dict so the background task in the route can persist history
    answer_text = "".join(full_answer)
    state.update(
        answer=answer_text,
        confidence=_determine_confidence(chunks[0].score),
        tokens_used=total_tokens,
        sources=[s.model_dump() for s in sources],
    )

    logger.info(
        "qa.streamed",
        question=question[:100],
        confidence=state["confidence"],
        top_score=chunks[0].score,
        tokens_used=total_tokens,
        model=MODEL,
    )


async def save_history_background(
    question: str,
    answer: str,
    confidence: str,
    tokens_used: int,
    sources: list[dict],
) -> None:
    """Creates its own DB session — called as a FastAPI BackgroundTask
    so it runs after the streaming response has been fully sent."""
    async with AsyncSessionLocal() as session:
        repo = HistoryRepository(session)
        await repo.save_interaction(question, answer, confidence, tokens_used, sources)
        await session.commit()

"""
RAG evaluation metrics.

Three LLM-as-judge metrics, each using a single GPT-4o-mini call per question:

  Faithfulness   — does the answer stay grounded in retrieved sources?
                   Splits the answer into sentences, asks the LLM which are
                   supported by the context. Score = supported / total.
                   Detects hallucination.

  Relevance      — did retrieval return the right chunks?
                   Asks the LLM to score each chunk 1-5 for relevance to
                   the question. Low scores mean retrieval is misfiring.

  Completeness   — does the answer address all aspects of the question?
                   Single 1-5 rating with a written explanation of any gaps.

All three use JSON mode for reliable parsing. One OpenAI client per call
to avoid connection-pool contention across concurrent evaluation runs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog
from openai import AsyncOpenAI

from app.config import settings

logger = structlog.get_logger()

JUDGE_MODEL = "gpt-4o-mini"


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class FaithfulnessResult:
    score: float  # 0.0–1.0 (supported_sentences / total_sentences)
    supported: int
    total: int
    sentence_results: list[dict] = field(default_factory=list)
    # e.g. [{"num": 1, "sentence": "...", "supported": True, "evidence": "..."}]


@dataclass
class RelevanceResult:
    score: float  # 0.0–1.0 (raw_score normalised from 1-5 scale)
    raw_score: float  # 1.0–5.0 average across all chunks
    chunk_scores: list[dict] = field(default_factory=list)
    # e.g. [{"chunk_num": 1, "score": 4, "reason": "..."}]


@dataclass
class CompletenessResult:
    score: float  # 0.0–1.0 (raw_score normalised from 1-5 scale)
    raw_score: float  # 1.0–5.0
    explanation: str = ""
    missing_aspects: list[str] = field(default_factory=list)


# ── Sentence splitter ─────────────────────────────────────────────────────────


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter that handles markdown-formatted LLM output.

    We strip markdown markers before splitting so "- Revenue was $X" becomes
    "Revenue was $X" rather than a fragment starting with "-".
    Filters out fragments shorter than 5 words — these are usually headers,
    list prefixes, or citation artefacts, not evaluable claims.
    """
    # Remove markdown headers (##, ###, etc.) and bullet markers
    clean = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    clean = re.sub(r"^\s*[-*•]\s+", "", clean, flags=re.MULTILINE)

    # Split on sentence-ending punctuation followed by whitespace, or on newlines
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean)
    return [p.strip() for p in parts if len(p.split()) >= 5]


# ── Shared JSON parser ────────────────────────────────────────────────────────


def _parse_json(raw: str, default: dict) -> dict:
    """Best-effort JSON extraction from an LLM response.

    GPT sometimes wraps JSON in a markdown code fence even in JSON mode —
    this strips the fence before parsing.
    """
    # Strip ```json ... ``` fence if present
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("eval.json_parse_failed", raw=raw[:200])
        return default


# ── Metric 1: Faithfulness ────────────────────────────────────────────────────


async def evaluate_faithfulness(answer: str, context: str) -> FaithfulnessResult:
    """Check what fraction of answer sentences are grounded in the context.

    One LLM call checks all sentences in a single batch to minimise latency.
    If the answer itself says "no relevant content found", we skip the check
    and return a full-score result (the answer is correctly grounded — there
    was nothing to hallucinate from).
    """
    if "no relevant content" in answer.lower() or "does not contain" in answer.lower():
        return FaithfulnessResult(score=1.0, supported=0, total=0)

    sentences = _split_sentences(answer)
    if not sentences:
        return FaithfulnessResult(score=1.0, supported=0, total=0)

    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))

    prompt = (
        "You are a factual grounding evaluator.\n\n"
        "CONTEXT (what the assistant had access to):\n"
        f"{context}\n\n"
        "ANSWER SENTENCES TO EVALUATE:\n"
        f"{numbered}\n\n"
        "For each sentence, determine whether it is DIRECTLY SUPPORTED by the context.\n"
        "A sentence is supported if its core claim can be verified in the context above.\n"
        "A sentence is NOT supported if it introduces facts not present in the context.\n"
        'Respond with JSON: {"sentences": [{"num": 1, "supported": true, "evidence": "quote from context or n/a"}, ...]}'
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or "{}"
    data = _parse_json(raw, {"sentences": []})
    results = data.get("sentences", [])

    supported = sum(1 for r in results if r.get("supported", False))
    total = len(results) if results else len(sentences)

    # Zip back to include the original sentence text for readability in reports
    enriched = []
    for i, r in enumerate(results):
        enriched.append(
            {
                "num": r.get("num", i + 1),
                "sentence": sentences[i] if i < len(sentences) else "",
                "supported": r.get("supported", False),
                "evidence": r.get("evidence", ""),
            }
        )

    return FaithfulnessResult(
        score=supported / total if total > 0 else 1.0,
        supported=supported,
        total=total,
        sentence_results=enriched,
    )


# ── Metric 2: Relevance ───────────────────────────────────────────────────────


async def evaluate_relevance(question: str, chunk_texts: list[str]) -> RelevanceResult:
    """Score each retrieved chunk for relevance to the question (1–5).

    One LLM call evaluates all chunks. Low scores across the board indicate
    the retrieval step is pulling semantically adjacent but wrong content.
    """
    if not chunk_texts:
        return RelevanceResult(score=0.0, raw_score=0.0)

    numbered_chunks = "\n\n".join(
        f"[Chunk {i + 1}]\n{text[:600]}" for i, text in enumerate(chunk_texts)
    )

    prompt = (
        "You are a retrieval quality evaluator.\n\n"
        f"QUESTION: {question}\n\n"
        "RETRIEVED CHUNKS:\n"
        f"{numbered_chunks}\n\n"
        "Rate each chunk's relevance to the question on a scale of 1–5:\n"
        "  1 = Completely unrelated to the question\n"
        "  2 = Same domain but addresses a different aspect\n"
        "  3 = Partially relevant — touches the topic but misses key info\n"
        "  4 = Highly relevant — directly useful for answering\n"
        "  5 = Perfect match — directly answers the question\n\n"
        'Respond with JSON: {"chunks": [{"chunk_num": 1, "score": 4, "reason": "..."}, ...]}'
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or "{}"
    data = _parse_json(raw, {"chunks": []})
    chunk_scores = data.get("chunks", [])

    scores = [r.get("score", 1) for r in chunk_scores if isinstance(r.get("score"), (int, float))]
    raw_score = sum(scores) / len(scores) if scores else 1.0
    normalised = (raw_score - 1) / 4  # map 1–5 → 0–1

    return RelevanceResult(
        score=round(normalised, 4),
        raw_score=round(raw_score, 4),
        chunk_scores=chunk_scores,
    )


# ── Metric 3: Completeness ────────────────────────────────────────────────────


async def evaluate_completeness(question: str, answer: str, context: str) -> CompletenessResult:
    """Rate how fully the answer addresses all aspects of the question (1–5)."""
    prompt = (
        "You are an answer quality evaluator.\n\n"
        f"QUESTION: {question}\n\n"
        "AVAILABLE CONTEXT:\n"
        f"{context[:2000]}\n\n"
        "ANSWER GIVEN:\n"
        f"{answer}\n\n"
        "Rate the completeness of the answer on a scale of 1–5:\n"
        "  1 = Completely ignores the question\n"
        "  2 = Addresses it minimally, major gaps\n"
        "  3 = Partially complete — covers the main point but misses details\n"
        "  4 = Mostly complete — minor aspects unaddressed\n"
        "  5 = Fully addresses all aspects of the question\n\n"
        "Respond with JSON: "
        '{"score": 4, "explanation": "...", "missing_aspects": ["aspect not covered", ...]}'
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or "{}"
    data = _parse_json(raw, {"score": 3, "explanation": "", "missing_aspects": []})

    raw_score = float(data.get("score", 3))
    raw_score = max(1.0, min(5.0, raw_score))  # clamp to [1, 5]
    normalised = (raw_score - 1) / 4

    return CompletenessResult(
        score=round(normalised, 4),
        raw_score=round(raw_score, 4),
        explanation=data.get("explanation", ""),
        missing_aspects=data.get("missing_aspects", []),
    )

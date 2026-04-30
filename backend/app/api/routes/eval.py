"""
POST /eval/run — runs the full RAG evaluation suite.

Flow per question:
  1. Retrieve chunks (timed)
  2. Generate answer via the QA pipeline (timed)
  3. Compute faithfulness, relevance, completeness in parallel

Questions run with a semaphore (max 3 concurrent) to stay within
OpenAI rate limits while still being meaningfully faster than serial.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.evaluation.evaluator import (
    evaluate_completeness,
    evaluate_faithfulness,
    evaluate_relevance,
)
from app.services.retrieval_service import retrieve_with_filter
from app.services.qa_service import answer_question
from app.db.session import AsyncSessionLocal

logger = structlog.get_logger()
router = APIRouter(tags=["evaluation"])

DATASET_PATH = Path(__file__).parents[3] / "evaluation" / "test_dataset.json"

# Limit concurrent question evaluations to avoid OpenAI rate limits.
# Each question makes 4+ LLM calls; 3 concurrent = up to 12 simultaneous calls.
_SEMAPHORE = asyncio.Semaphore(3)


# ── Response schemas ──────────────────────────────────────────────────────────


class EvalQuestionResult(BaseModel):
    id: str
    question: str
    answer: str
    # Faithfulness
    faithfulness: float
    faithfulness_supported: int
    faithfulness_total: int
    # Relevance (retrieval quality)
    relevance: float
    relevance_raw: float
    # Completeness
    completeness: float
    completeness_raw: float
    completeness_explanation: str
    # Latency
    retrieval_latency_ms: float
    total_latency_ms: float
    # Non-null if the question itself errored (e.g. OpenAI timeout)
    error: str | None = None


class EvalReport(BaseModel):
    timestamp: str
    total_questions: int
    avg_faithfulness: float
    avg_relevance: float
    avg_completeness: float
    avg_retrieval_latency_ms: float
    avg_total_latency_ms: float
    results: list[EvalQuestionResult]


# ── Per-question evaluation ───────────────────────────────────────────────────


async def _eval_one(item: dict) -> EvalQuestionResult:
    """Run the full pipeline + all metrics for a single test question."""
    question = item["question"]
    qid = item.get("id", question[:20])

    try:
        # ── Step 1: Retrieval (timed separately) ─────────────────────────────
        t_start = time.perf_counter()
        chunks, _warning = await retrieve_with_filter(question, top_k=5)
        retrieval_ms = (time.perf_counter() - t_start) * 1000

        # ── Step 2: Generation (timed as part of total) ───────────────────────
        async with AsyncSessionLocal() as db:
            answer_resp = await answer_question(question, document_ids=None, db=db)
        total_ms = (time.perf_counter() - t_start) * 1000

        answer = answer_resp.answer
        chunk_texts = [c.text for c in chunks]
        context = "\n\n---\n\n".join(chunk_texts) if chunk_texts else ""

        # ── Step 3: Metrics in parallel ───────────────────────────────────────
        faith_task = evaluate_faithfulness(answer, context)
        rel_task = evaluate_relevance(question, chunk_texts)
        comp_task = evaluate_completeness(question, answer, context)

        faith, rel, comp = await asyncio.gather(faith_task, rel_task, comp_task)

        logger.info(
            "eval.question.done",
            id=qid,
            faithfulness=round(faith.score, 3),
            relevance=round(rel.raw_score, 2),
            completeness=round(comp.raw_score, 2),
            retrieval_ms=round(retrieval_ms),
            total_ms=round(total_ms),
        )

        return EvalQuestionResult(
            id=qid,
            question=question,
            answer=answer,
            faithfulness=round(faith.score, 4),
            faithfulness_supported=faith.supported,
            faithfulness_total=faith.total,
            relevance=round(rel.score, 4),
            relevance_raw=round(rel.raw_score, 2),
            completeness=round(comp.score, 4),
            completeness_raw=round(comp.raw_score, 2),
            completeness_explanation=comp.explanation,
            retrieval_latency_ms=round(retrieval_ms, 1),
            total_latency_ms=round(total_ms, 1),
        )

    except Exception as exc:
        logger.error("eval.question.error", id=qid, error=str(exc))
        return EvalQuestionResult(
            id=qid,
            question=question,
            answer="",
            faithfulness=0.0,
            faithfulness_supported=0,
            faithfulness_total=0,
            relevance=0.0,
            relevance_raw=0.0,
            completeness=0.0,
            completeness_raw=0.0,
            completeness_explanation="",
            retrieval_latency_ms=0.0,
            total_latency_ms=0.0,
            error=str(exc),
        )


async def _eval_one_with_sem(item: dict) -> EvalQuestionResult:
    async with _SEMAPHORE:
        return await _eval_one(item)


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/eval/run", response_model=EvalReport)
async def run_evaluation() -> EvalReport:
    """Run all test questions and return a full evaluation report.

    Takes ~30–60 s depending on OpenAI latency. The frontend should
    show a loading indicator while waiting.
    """
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Test dataset not found: {DATASET_PATH}")

    dataset = json.loads(DATASET_PATH.read_text())
    logger.info("eval.run.start", total_questions=len(dataset))
    t0 = time.perf_counter()

    results = await asyncio.gather(*[_eval_one_with_sem(item) for item in dataset])

    # Exclude errored questions from averages so one failure doesn't tank all metrics
    valid = [r for r in results if r.error is None]

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    from datetime import datetime, timezone

    report = EvalReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_questions=len(results),
        avg_faithfulness=_avg([r.faithfulness for r in valid]),
        avg_relevance=_avg([r.relevance_raw for r in valid]),
        avg_completeness=_avg([r.completeness_raw for r in valid]),
        avg_retrieval_latency_ms=_avg([r.retrieval_latency_ms for r in valid]),
        avg_total_latency_ms=_avg([r.total_latency_ms for r in valid]),
        results=list(results),
    )

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "eval.run.complete",
        valid=len(valid),
        errored=len(results) - len(valid),
        elapsed_ms=elapsed,
    )
    return report

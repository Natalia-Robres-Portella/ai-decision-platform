from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.repositories.history_repository import HistoryRepository
from app.schemas.answer import AnswerResponse, QueryHistoryEntry, QuestionRequest
from app.services.qa_service import (
    answer_question,
    save_history_background,
    stream_answer_tokens,
)

router = APIRouter(tags=["qa"])


@router.post("/ask", response_model=AnswerResponse, status_code=200)
async def ask(
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    """Ask a question against the ingested documents.

    The full answer is returned in one response. Use /ask/stream if you
    want token-by-token output for a better UX on long answers.
    """
    return await answer_question(
        question=request.question,
        document_ids=request.document_ids,
        db=db,
    )


@router.post("/ask/stream")
async def ask_stream(
    request: QuestionRequest,
    background_tasks: BackgroundTasks,
) -> StreamingResponse:
    """Stream the LLM answer token by token via Server-Sent Events.

    Connect with EventSource (browser) or an SSE client library.
    Each event is a JSON object with a 'type' field:

      data: {"type": "token",   "content": "Tesla's"}
      data: {"type": "token",   "content": " revenue"}
      ...
      data: {"type": "sources", "content": [{...}, {...}]}
      data: [DONE]

    The history save is deferred to a background task that runs after the
    last byte is sent, so streaming latency is unaffected.
    """
    # Mutable dict that stream_answer_tokens populates at the end of the stream.
    # The background task reads from it after the response completes.
    state: dict = {}

    async def generate():
        async for event in stream_answer_tokens(request.question, request.document_ids, state):
            yield event

    async def persist_history():
        if state:  # only save if stream completed (not on error/early exit)
            await save_history_background(
                question=request.question,
                answer=state.get("answer", ""),
                confidence=state.get("confidence", "low"),
                tokens_used=state.get("tokens_used", 0),
                sources=state.get("sources", []),
            )

    background_tasks.add_task(persist_history)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx response buffering
            "Connection": "keep-alive",
        },
    )


@router.get("/history", response_model=list[QueryHistoryEntry])
async def get_history(
    db: AsyncSession = Depends(get_db),
) -> list[QueryHistoryEntry]:
    """Return the 20 most recent Q&A interactions, newest first."""
    repo = HistoryRepository(db)
    entries = await repo.list_recent(limit=20)
    return [QueryHistoryEntry.model_validate(e) for e in entries]

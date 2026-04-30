from fastapi import APIRouter

from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval_service import (
    retrieve_relevant_chunks,
    retrieve_with_filter,
)

router = APIRouter(prefix="/retrieve", tags=["retrieval"])


@router.post("", response_model=RetrievalResponse)
async def retrieve(request: RetrievalRequest) -> RetrievalResponse:
    """Find the most semantically relevant chunks for a query.

    When document_ids is provided, search is restricted to those documents only.
    Useful for "ask about this specific report" UX flows.
    """
    if request.document_ids:
        chunks, warning = await retrieve_with_filter(
            query=request.query,
            top_k=request.top_k,
            document_ids=request.document_ids,
            score_threshold=request.score_threshold,
        )
    else:
        chunks, warning = await retrieve_relevant_chunks(
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )

    return RetrievalResponse(
        query=request.query,
        chunks=chunks,
        total_found=len(chunks),
        warning=warning,
    )

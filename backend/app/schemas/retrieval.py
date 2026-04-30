from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    text: str
    score: float
    document_id: str
    filename: str
    page_number: int
    chunk_index: int


class RetrievalRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] | None = None
    # Expose the threshold per-request so callers can tune it for their use case.
    # Default 0.6 explained in retrieval_service.py.
    score_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class RetrievalResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    total_found: int
    warning: str | None = None

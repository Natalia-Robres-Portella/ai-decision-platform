from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SourceReference(BaseModel):
    filename: str
    page_number: int
    relevance_score: float
    excerpt: str  # first ~200 chars of the chunk, enough to show provenance


class AnswerResponse(BaseModel):
    query: str
    answer: str
    sources: list[SourceReference]
    confidence: Literal["high", "medium", "low"]
    model_used: str
    tokens_used: int


class QuestionRequest(BaseModel):
    question: str
    document_ids: list[str] | None = None


class QueryHistoryEntry(BaseModel):
    id: str
    question: str
    answer: str
    confidence: str
    tokens_used: int
    sources: list[dict] | None  # stored as JSON in Postgres, returned as list here
    created_at: datetime

    model_config = {"from_attributes": True}

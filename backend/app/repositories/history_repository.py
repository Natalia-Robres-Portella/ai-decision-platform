import uuid

from sqlalchemy import select

from app.db.models import QueryHistory
from app.repositories.base import BaseRepository


class HistoryRepository(BaseRepository):
    async def save_interaction(
        self,
        question: str,
        answer: str,
        confidence: str,
        tokens_used: int,
        sources: list[dict],
    ) -> QueryHistory:
        entry = QueryHistory(
            id=str(uuid.uuid4()),
            question=question,
            answer=answer,
            confidence=confidence,
            tokens_used=tokens_used,
            sources=sources,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_recent(self, limit: int = 20) -> list[QueryHistory]:
        result = await self.session.execute(
            select(QueryHistory).order_by(QueryHistory.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

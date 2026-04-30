from sqlalchemy import select

from app.db.models import Document
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    async def save_document_metadata(
        self,
        document_id: str,
        filename: str,
        status: str,
        num_chunks: int | None,
        file_path: str | None = None,
    ) -> Document:
        doc = Document(
            id=document_id,
            filename=filename,
            status=status,
            num_chunks=num_chunks,
            file_path=file_path,
        )
        self.session.add(doc)
        # flush writes to DB within the current transaction without committing.
        # The commit happens automatically when the request finishes (see get_db).
        await self.session.flush()
        return doc

    async def get_document_by_id(self, document_id: str) -> Document | None:
        result = await self.session.execute(select(Document).where(Document.id == document_id))
        return result.scalar_one_or_none()

    async def list_documents(self) -> list[Document]:
        result = await self.session.execute(select(Document).order_by(Document.created_at.desc()))
        return list(result.scalars().all())

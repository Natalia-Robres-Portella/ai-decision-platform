from datetime import datetime

from pydantic import BaseModel


class DocumentIngestResponse(BaseModel):
    document_id: str
    filename: str
    num_chunks: int
    status: str


class DocumentMetadata(BaseModel):
    id: str
    filename: str
    status: str
    num_chunks: int | None
    file_path: str | None
    created_at: datetime

    # from_attributes=True lets Pydantic read from SQLAlchemy ORM objects
    # (previously called orm_mode in Pydantic v1)
    model_config = {"from_attributes": True}

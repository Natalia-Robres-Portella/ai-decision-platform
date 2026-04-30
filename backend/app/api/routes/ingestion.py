import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.config import settings
from app.models.document import DocumentIngestResponse, DocumentMetadata
from app.repositories.document_repository import DocumentRepository
from app.services.ingestion_service import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/ingest", response_model=DocumentIngestResponse, status_code=201)
async def ingest_pdf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentIngestResponse:
    """Accept a PDF upload, run the ingestion pipeline, return the result.

    Flow:
      1. Validate file type
      2. Generate document_id and persist the file to disk
      3. Write a "processing" record to Postgres (so the document is trackable
         even if ingestion fails partway through)
      4. Run the pipeline (load → chunk → embed → store in Qdrant)
      5. Update Postgres record to "completed"
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    document_id = str(uuid.uuid4())
    raw_dir = Path(settings.data_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / f"{document_id}.pdf"

    # Persist the raw file — lets us re-process with updated pipelines later
    with file_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    repo = DocumentRepository(db)

    # Write the initial record before ingestion starts.
    # If the server crashes mid-pipeline, we can see "processing" documents
    # and know they need re-ingestion.
    await repo.save_document_metadata(
        document_id=document_id,
        filename=file.filename,
        status="processing",
        num_chunks=None,
        file_path=str(file_path),
    )

    try:
        num_chunks = await ingest_document(
            file_path=str(file_path),
            document_id=document_id,
            filename=file.filename,
        )
    except Exception as exc:
        doc = await repo.get_document_by_id(document_id)
        if doc:
            doc.status = "failed"
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    doc = await repo.get_document_by_id(document_id)
    if doc:
        doc.status = "completed"
        doc.num_chunks = num_chunks

    return DocumentIngestResponse(
        document_id=document_id,
        filename=file.filename,
        num_chunks=num_chunks,
        status="completed",
    )


@router.get("", response_model=list[DocumentMetadata])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[DocumentMetadata]:
    repo = DocumentRepository(db)
    docs = await repo.list_documents()
    return [DocumentMetadata.model_validate(doc) for doc in docs]


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> DocumentMetadata:
    repo = DocumentRepository(db)
    doc = await repo.get_document_by_id(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentMetadata.model_validate(doc)

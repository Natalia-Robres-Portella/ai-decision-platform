"""
Document ingestion pipeline.

Data flow:
  PDF file → load_pdf() → pages (text per page)
           → chunk_document() → text chunks (token windows with overlap)
           → embed_and_store() → vectors stored in Qdrant
"""

import asyncio
import uuid

import tiktoken
from openai import AsyncOpenAI
from pypdf import PdfReader
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from app.config import settings

# cl100k_base is the tokenizer OpenAI uses for text-embedding-3-small.
# Using the exact same tokenizer means our chunk_size is accurate in model tokens,
# not estimated character counts.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50  # tokens


# ---------------------------------------------------------------------------
# Step 1: Load
# ---------------------------------------------------------------------------


def load_pdf(file_path: str) -> list[dict]:
    """Read a PDF and return a list of {page_number, text} dicts.

    Why page-level granularity?
    Preserving page numbers in the Qdrant payload lets the retrieval layer
    tell the user exactly where in the source document an answer came from.
    Source citations are what make RAG answers trustworthy and auditable.
    """
    if not file_path.lower().endswith(".pdf"):
        raise ValueError(f"Unsupported file type: {file_path}. Only PDF files are accepted.")
    reader = PdfReader(file_path)
    pages = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():  # skip blank or image-only pages
            pages.append({"page_number": page_num, "text": text})
    return pages


# ---------------------------------------------------------------------------
# Step 2: Chunk
# ---------------------------------------------------------------------------


def chunk_document(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """Split text into overlapping token windows.

    Why 512 tokens?
    Small enough for precise retrieval (a large chunk retrieved for a narrow
    question brings in irrelevant context), large enough to carry a full
    paragraph. text-embedding-3-small accepts up to 8191 tokens, but smaller
    chunks → better precision.

    Why 50-token overlap?
    When a sentence falls exactly on a chunk boundary, it would be split in two.
    The overlap ensures that boundary sentence appears complete in at least one
    chunk — the tail of the previous and the head of the next.
    Without overlap: "The revenue was $4.2" | "billion in Q3" — neither chunk
    is coherent on its own.
    With overlap: both chunks include the full sentence.

    Implementation: sliding window over a flat token list, then decode back to
    text. This is the same strategy used by LlamaIndex's SentenceSplitter
    internally, made explicit here so you can see every step.
    """
    tokens = _TOKENIZER.encode(text)

    if not tokens:
        return []

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(_TOKENIZER.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += chunk_size - overlap  # slide forward, keeping `overlap` tokens

    return chunks


# ---------------------------------------------------------------------------
# Step 3: Embed + Store
# ---------------------------------------------------------------------------


async def embed_and_store(
    chunks: list[dict],  # [{text, page_number, chunk_index}, ...]
    document_id: str,
    metadata: dict,  # {filename, source_type}
) -> None:
    """Embed chunks with OpenAI text-embedding-3-small and upsert into Qdrant.

    Why batch the embedding call?
    OpenAI's API accepts a list of strings in one request. Sending all chunks
    at once eliminates N-1 round-trip latencies (one big call vs one per chunk).
    For a 50-page document that produces ~200 chunks, this saves ~199 HTTP
    round trips.

    Why store `text` in the Qdrant payload?
    At query time we need to pass the original chunk text to the LLM as context.
    Storing it in the payload means one Qdrant call returns both the matching
    vectors AND the text — no second database round trip.
    """
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    qdrant_client = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

    try:
        texts = [c["text"] for c in chunks]

        # Single API call — all chunks embedded in one round trip
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        embeddings = [item.embedding for item in response.data]

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "document_id": document_id,
                    "filename": metadata["filename"],
                    "page_number": chunk["page_number"],
                    "chunk_index": chunk["chunk_index"],
                    "source_type": metadata.get("source_type", "pdf"),
                    "text": chunk["text"],
                },
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]

        # Upsert in batches to stay within Qdrant's request payload limits
        batch_size = 100
        for i in range(0, len(points), batch_size):
            await qdrant_client.upsert(
                collection_name=settings.collection_name,
                points=points[i : i + batch_size],
            )
    finally:
        await qdrant_client.close()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def ingest_document(file_path: str, document_id: str, filename: str) -> int:
    """Run the full pipeline. Returns the total number of chunks stored.

    load_pdf and chunk_document are synchronous (CPU/IO-bound).
    asyncio.to_thread() pushes them to a thread-pool worker so they don't
    block the event loop while the server handles other requests.
    """
    pages = await asyncio.to_thread(load_pdf, file_path)

    all_chunks: list[dict] = []
    for page in pages:
        chunk_texts = await asyncio.to_thread(chunk_document, page["text"])
        for text in chunk_texts:
            all_chunks.append(
                {
                    "text": text,
                    "page_number": page["page_number"],
                    "chunk_index": len(all_chunks),
                }
            )

    await embed_and_store(
        chunks=all_chunks,
        document_id=document_id,
        metadata={"filename": filename, "source_type": "pdf"},
    )

    return len(all_chunks)

"""
Shared fixtures for the test suite.

Strategy:
  - Unit tests get individual service functions patched in isolation.
  - Integration tests get a full ASGI client with:
      * SQLite in-memory replacing Postgres (aiosqlite driver, same ORM schema)
      * Qdrant lifespan patched out so no running Qdrant is needed
      * OpenAI calls mocked at the httpx transport level (via patch)

Two key fixtures drive everything:
  db_session  — bare SQLAlchemy session against SQLite, for unit tests that
                touch the DB directly (e.g. history_repository tests).
  client      — httpx.AsyncClient pointed at the FastAPI app, for integration
                tests. All external I/O is mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app

# ---------------------------------------------------------------------------
# SQLite in-memory engine (no Postgres required)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    """AsyncSession backed by SQLite in-memory.

    Creates all ORM tables before the test and drops them after, so each
    test starts with a clean schema.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Full ASGI client with all external deps mocked
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session):
    """httpx.AsyncClient wired to the FastAPI app.

    Patches applied for every integration test:
      1. app.main.AsyncQdrantClient  — prevents lifespan from connecting to Qdrant
      2. app.main.engine             — replaced by the SQLite engine so create_all
                                       runs against SQLite, not Postgres
    The db_session is injected via FastAPI's DI so route handlers get the
    same SQLite session the test can inspect.
    """
    sqlite_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    sqlite_session_factory = async_sessionmaker(
        sqlite_engine, expire_on_commit=False, class_=AsyncSession
    )

    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with sqlite_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    mock_qdrant = AsyncMock()
    mock_qdrant.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    mock_qdrant.create_collection = AsyncMock()
    mock_qdrant.close = AsyncMock()

    with (
        patch("app.main.AsyncQdrantClient", return_value=mock_qdrant),
        patch("app.main.engine", sqlite_engine),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()

    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await sqlite_engine.dispose()


# ---------------------------------------------------------------------------
# Mock object factories
# ---------------------------------------------------------------------------


def make_qdrant_point(
    score: float = 0.85,
    text: str = "Tesla Q4 revenue was $25.2 billion.",
    filename: str = "tesla.pdf",
    page_number: int = 3,
    document_id: str = "doc-001",
    chunk_index: int = 0,
) -> MagicMock:
    """Construct a Qdrant ScoredPoint-like mock the retrieval service can consume."""
    point = MagicMock()
    point.score = score
    point.payload = {
        "text": text,
        "filename": filename,
        "page_number": page_number,
        "document_id": document_id,
        "chunk_index": chunk_index,
        "source_type": "pdf",
    }
    return point


def make_query_response(points: list) -> MagicMock:
    """Wrap a list of points in a QueryResponse-like mock."""
    resp = MagicMock()
    resp.points = points
    return resp


def make_openai_embedding(dims: int = 1536) -> list[float]:
    """Return a unit vector of length `dims` for use as a mock embedding."""
    return [1.0 / dims] * dims


def make_openai_embedding_response(dims: int = 1536) -> MagicMock:
    """Mock of the object returned by openai_client.embeddings.create()."""
    item = MagicMock()
    item.embedding = make_openai_embedding(dims)
    resp = MagicMock()
    resp.data = [item]
    return resp


def make_chat_completion(content: str = "The answer is 42.", total_tokens: int = 150) -> MagicMock:
    """Mock of the object returned by openai_client.chat.completions.create()."""
    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.total_tokens = total_tokens

    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


def make_minimal_pdf_bytes() -> bytes:
    """Return a minimal valid PDF as bytes.

    pypdf can parse this — it is the smallest self-contained PDF structure.
    Used to avoid shipping a test fixture file.
    """
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n"
        b"0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n441\n%%EOF"
    )

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

# Import models so SQLAlchemy's metadata is aware of all tables before create_all
import app.db.models  # noqa: F401
from app.api.routes import health, ingestion, qa, retrieval
from app.config import settings
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # --- Startup ---
    setup_logging(debug=settings.debug)

    # Create PostgreSQL tables (dev convenience — replace with Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create Qdrant collection if it doesn't exist.
    # 1536 = output dimension of text-embedding-3-small.
    # Cosine distance = standard for semantic similarity (measures angle, not magnitude).
    qdrant = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    existing = {c.name for c in (await qdrant.get_collections()).collections}
    if settings.collection_name not in existing:
        await qdrant.create_collection(
            collection_name=settings.collection_name,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
    await qdrant.close()

    yield

    # --- Shutdown ---
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(ingestion.router, prefix="/api/v1")
    app.include_router(retrieval.router, prefix="/api/v1")
    app.include_router(qa.router, prefix="/api/v1")

    return app


app = create_app()

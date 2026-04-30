from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.main import app


async def mock_db_session():
    """Override the real DB session with a mock for unit tests."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    yield session


@pytest.mark.asyncio
async def test_health_check_returns_ok():
    app.dependency_overrides[get_db] = mock_db_session

    with patch("app.services.health.AsyncQdrantClient") as mock_qdrant_cls:
        mock_client = AsyncMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.get_collections = AsyncMock(return_value=[])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert "database" in body["components"]
    assert "qdrant" in body["components"]
    assert body["components"]["database"]["status"] == "ok"
    assert body["components"]["qdrant"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_degraded_when_db_fails():
    async def broken_db():
        session = AsyncMock(spec=AsyncSession)
        session.execute = AsyncMock(side_effect=Exception("Connection refused"))
        yield session

    app.dependency_overrides[get_db] = broken_db

    with patch("app.services.health.AsyncQdrantClient") as mock_qdrant_cls:
        mock_client = AsyncMock()
        mock_qdrant_cls.return_value = mock_client
        mock_client.get_collections = AsyncMock(return_value=[])

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"]["status"] == "error"

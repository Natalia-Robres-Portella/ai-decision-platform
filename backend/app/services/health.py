from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.health import ComponentHealth, HealthResponse


class HealthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check(self) -> HealthResponse:
        db_health = await self._check_database()
        qdrant_health = await self._check_qdrant()

        components: dict[str, ComponentHealth] = {
            "database": db_health,
            "qdrant": qdrant_health,
        }

        all_ok = all(c.status == "ok" for c in components.values())
        return HealthResponse(
            status="ok" if all_ok else "degraded",
            version="0.1.0",
            components=components,
        )

    async def _check_database(self) -> ComponentHealth:
        try:
            await self.db.execute(text("SELECT 1"))
            return ComponentHealth(status="ok", message="Connected")
        except Exception as exc:
            return ComponentHealth(status="error", message=str(exc))

    async def _check_qdrant(self) -> ComponentHealth:
        try:
            client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
            await client.get_collections()
            await client.close()
            return ComponentHealth(status="ok", message="Connected")
        except Exception as exc:
            return ComponentHealth(status="error", message=str(exc))

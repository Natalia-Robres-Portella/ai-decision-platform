from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """All repositories inherit from this to get a shared DB session interface."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

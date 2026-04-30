from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Walk up from backend/app/ → backend/ → project root to find .env
# This works regardless of which directory uvicorn is invoked from.
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # silently skip env vars not declared in this class
    )

    app_name: str = "AI Decision Intelligence Platform"
    app_env: str = "development"
    debug: bool = False

    # PostgreSQL
    postgres_user: str = "admin"
    postgres_password: str = "password"
    postgres_db: str = "ai_decision_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    collection_name: str = "documents"

    # OpenAI
    openai_api_key: str = ""

    # Storage: where uploaded PDFs are saved on disk
    data_dir: str = "data"


# Single shared instance imported throughout the app
settings = Settings()

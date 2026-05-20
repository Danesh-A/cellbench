"""Runtime configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    All values can be overridden by environment variables of the same
    name (case-insensitive). See `.env.example` at the repo root for the
    canonical list.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ----------------------------------------------------------
    env: str = Field("dev", description="One of dev | staging | prod")
    log_level: str = "INFO"

    # --- Database ------------------------------------------------------
    database_url: str = "postgresql+psycopg://cellbench:cellbench@db:5432/cellbench"

    # --- Auth ----------------------------------------------------------
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expires_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # --- Object storage -----------------------------------------------
    s3_endpoint_url: str | None = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "cellbench"
    s3_public_url: str | None = "http://localhost:9000"
    presigned_url_ttl: int = 60 * 15  # 15 minutes

    # --- CORS ----------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """Cache the Settings instance for the lifetime of the process."""
    return Settings()

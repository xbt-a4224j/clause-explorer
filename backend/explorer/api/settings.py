"""Runtime configuration.

Every value is env-overridable so the same image runs under compose, in CI, and locally.
Defaults point at the compose service names.

The env var names are the ones docker-compose already sets (CLAUSE_EXPLORER_DB,
CUBE_API_URL), so they are mapped explicitly rather than via a prefix convention that
would silently rename both.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://explorer:explorer@localhost:5432/explorer"
    cube_api_url: str = "http://localhost:4000/cubejs-api/v1"
    log_level: str = "INFO"

    # Present only so generation and fresh embeddings can work. The app must boot and
    # serve retrieval, facets, coverage and every table view without it.
    openai_api_key: str | None = None

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "CLAUSE_EXPLORER_DB",
            "postgresql://explorer:explorer@localhost:5432/explorer",
        ),
        cube_api_url=os.getenv("CUBE_API_URL", "http://localhost:4000/cubejs-api/v1"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
    )


settings = load_settings()

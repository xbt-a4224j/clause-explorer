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

    # Below this sample size a prevalence renders as "6 of 8", never "75%". A percentage
    # implies a precision the sample does not support, and it is the number a partner quotes
    # in a pitch. Config rather than a literal so the rendering rule is testable at its edge.
    percentage_threshold: int = 30

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
        percentage_threshold=int(os.getenv("PERCENTAGE_THRESHOLD", "30")),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
    )


settings = load_settings()

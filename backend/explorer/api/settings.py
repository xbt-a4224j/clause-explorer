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

    # ── environment: differs per machine, never checked in ──────────────────────────────
    database_url: str = "postgresql://explorer:explorer@localhost:5432/explorer"
    cube_api_url: str = "http://localhost:4000/cubejs-api/v1"
    log_level: str = "INFO"

    # Below this sample size a prevalence renders as "6 of 8", never "75%". A percentage
    # implies a precision the sample does not support, and it is the number a partner quotes
    # in a pitch. Config rather than a literal so the rendering rule is testable at its edge.
    # ── policy: how this deployment chooses to behave. semantic-quorum takes these as
    #    ARGUMENTS rather than importing this object — a library that reaches into its caller's
    #    settings to find a threshold is the coupling the extraction exists to remove ────────
    percentage_threshold: int = 30

    # Below this, a slice is not characterized at all (#22 marks it, #23 refuses on it).
    # Three jobs: statistical honesty, extraction-confidence gating, and k-anonymity — an
    # attorney who can filter to n=1 has extracted one client's negotiated term through the
    # analytics layer without retrieving a document.
    min_n: int = 5

    # Deal points whose calibrated extraction accuracy (#28) falls below this are excluded from
    # any rollup, distinct from the min_n refusal. 0.7 is a placeholder rationale (typical
    # acceptability floor for an unreviewed classifier feeding a quoted figure) pending #28's
    # measured per-deal-point accuracy table — MAUD's own labels are gold and never gated by
    # this threshold; it exists for extractor output only.
    min_extraction_confidence: float = 0.7

    # Above this, a recorded span is document-scale rather than clause-scale and is shown as a
    # bounded excerpt, labelled as one. Measured over this corpus, MAUD's span lengths have a
    # median of 4,658 characters and a 90th percentile of 238,949 — the annotations mark where
    # in the agreement an answer was found, and for holistic deal points that is most of the
    # document. Rendering the raw slice as "the clause" showed a table of contents, which is the
    # exact failure this product exists to avoid: a wrong answer that looks like a finding.
    # 6,000 sits just above the median so genuinely clause-scale spans pass through whole.
    # ── presentation: what this corpus's documents look like, so domain rather than platform ──
    max_clause_chars: int = 6000

    # How much of a document-scale span is shown. Enough to see what kind of text the span
    # covers; short enough that nobody mistakes it for the operative language.
    excerpt_chars: int = 1200

    # Present only so generation and fresh embeddings can work. The app must boot and
    # serve retrieval, facets, the rollup and every table view without it.
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
        min_n=int(os.getenv("MIN_N", "5")),
        min_extraction_confidence=float(os.getenv("MIN_EXTRACTION_CONFIDENCE", "0.7")),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
    )


settings = load_settings()

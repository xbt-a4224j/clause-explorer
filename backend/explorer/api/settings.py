"""Runtime configuration — this DEPLOYMENT, not this corpus.

Every value here is env-overridable so the same image runs under compose, in CI, and locally.
The env var names are the ones docker-compose already sets (QUORUM_DB, CUBE_API_URL),
mapped explicitly rather than via a prefix convention that would silently rename both.

## What this object is no longer

It was a grab bag: a connection string, a log level, a disclosure threshold, and a measurement
of MAUD's span lengths in one place. Two changes fixed that, and only one of them is visible
here.

The important one is that `semantic-quorum` does not import this object. It takes `min_n`, the
Cube URL and the API key as ARGUMENTS — a library that reaches into its caller's settings to
find a threshold is exactly the coupling the extraction exists to remove, and it is what makes
the gate testable at its edge without a running app.

The second is that `max_clause_chars` and `excerpt_chars` moved to `quorum.yaml`. They are
per-CORPUS, justified by a measurement of this corpus's documents, and identical on every
machine. Sitting them next to a database URL implied they were something an operator tunes.

What is left divides cleanly, and the sections below say which is which: environment (differs
per machine, never checked in) and policy (how this deployment chooses to behave).
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

    # ── policy: how this deployment chooses to behave ───────────────────────────────────
    #
    # Below this sample size a prevalence renders as "6 of 8", never "75%". A percentage
    # implies a precision the sample does not support, and it is the number a partner quotes
    # in a pitch. Config rather than a literal so the rendering rule is testable at its edge.
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

    # Required to run the product. This used to say the app must boot and serve everything
    # without a key, a constraint written when nothing in the app called a model, so it cost
    # nothing to keep. It costs something now: the model sits on the user's path in Ask, and a
    # build that guarantees everything works without a key is a build whose headline feature is
    # the one thing that does not.
    openai_api_key: str | None = None

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)


def load_settings() -> Settings:
    return Settings(
        # QUORUM_DB is the platform's name and what `quorum migrate` reads; CLAUSE_EXPLORER_DB
        # is what this repo has set in compose, .env and people's shells for months. Honouring
        # both is not indecision — the cost of breaking a working setup is paid by a person, and
        # the benefit of a single name is paid to a document.
        database_url=(
            os.getenv("QUORUM_DB")
            or os.getenv("CLAUSE_EXPLORER_DB")
            or "postgresql://explorer:explorer@localhost:5432/explorer"
        ),
        cube_api_url=os.getenv("CUBE_API_URL", "http://localhost:4000/cubejs-api/v1"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        percentage_threshold=int(os.getenv("PERCENTAGE_THRESHOLD", "30")),
        min_n=int(os.getenv("MIN_N", "5")),
        min_extraction_confidence=float(os.getenv("MIN_EXTRACTION_CONFIDENCE", "0.7")),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
    )


settings = load_settings()

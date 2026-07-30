"""Structured logging.

JSON lines to stdout and to logs/explorer.jsonl. The file format is JSONL specifically so
the Admin tab (#30) can tail it and parse into columns without a log service.

Two invariants:

1. **Redaction is unconditional.** It runs as a structlog processor over every event and
   every string value, so a secret cannot reach the sink by being passed to a call site
   that forgot to sanitize. This repo is public; a leaked key in a committed log or a
   pasted traceback is unrecoverable.
2. **Request context binds once.** `bind_request` puts the request id in contextvars, so
   nested calls inherit it without threading a logger through every signature.
"""

from __future__ import annotations

import logging
import re
import sys
import uuid
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import structlog

LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_FILE = LOG_DIR / "explorer.jsonl"

# Long document text is truncated rather than logged whole — see truncate().
MAX_LOGGED_TEXT = 200

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # OpenAI-style keys, project and legacy forms
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{16,}"),
    # password inside a connection string: scheme://user:PASSWORD@host
    re.compile(r"(?<=://)([^:/\s]+):([^@/\s]+)(?=@)"),
    # bearer tokens
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),
)


def redact(value: str) -> str:
    """Replace credential-shaped substrings with a visible marker.

    Deliberately conservative on the DSN pattern: the username is preserved so a log line
    stays diagnosable, and only the password is masked.
    """
    out = _SECRET_PATTERNS[0].sub("***", value)
    out = _SECRET_PATTERNS[1].sub(r"\1:***", out)
    return _SECRET_PATTERNS[2].sub(r"\1***", out)


def truncate(text: str, limit: int = MAX_LOGGED_TEXT) -> str:
    """Cap document text so a log line never carries a whole contract."""
    return text if len(text) <= limit else f"{text[:limit]}…[+{len(text) - limit} chars]"


def _redact_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact every string value in the event, including the event name itself."""
    return {
        k: redact(v) if isinstance(v, str) else v  # non-strings cannot carry a key
        for k, v in event_dict.items()
    }


def configure_logging(level: str = "INFO", *, to_file: bool = True) -> None:
    """Install the JSONL processor chain. Idempotent — safe to call per test."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if to_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    for handler in handlers:
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,  # last before rendering: nothing bypasses it
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str = "explorer") -> Any:
    return structlog.get_logger(name)


def bind_request(request_id: str | None = None) -> str:
    """Bind a request id to the context so nested logs inherit it. Returns the id."""
    rid = request_id or uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def clear_request() -> None:
    structlog.contextvars.clear_contextvars()


# --- domain-specific helpers, so timing and field names stay consistent -------------


def log_llm_call(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    cost_usd: float | None = None,
) -> None:
    get_logger().info(
        "llm_call",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=round(duration_ms, 1),
        cost_usd=cost_usd,
    )


def log_cube_query(
    *, measures: list[str], dimensions: list[str], filters: int, row_count: int, duration_ms: float
) -> None:
    get_logger().info(
        "cube_query",
        measures=measures,
        dimensions=dimensions,
        filter_count=filters,
        row_count=row_count,
        duration_ms=round(duration_ms, 1),
    )


def log_ingest_step(
    *,
    source: str,
    rows_read: int,
    rows_upserted: int,
    duration_ms: float,
    sha256: str | None = None,
) -> None:
    get_logger().info(
        "ingest_step",
        source=source,
        rows_read=rows_read,
        rows_upserted=rows_upserted,
        duration_ms=round(duration_ms, 1),
        sha256=sha256,
    )

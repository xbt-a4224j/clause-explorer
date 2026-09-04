"""`GET /admin/*` — ingest status, calibration, evals, live log viewer (#30).

Built for one stated reason: Alex asked for logs and table views so he never has to open psql.
Ingest status and eval/calibration numbers are read from artefacts other issues already produce
(`ingest_runs`, `docs/results/*.md`) — this is composition, not new computation, so there is
exactly one place any of those numbers can drift from what actually ran.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query

from explorer.api.logging import redact
from explorer.api.settings import settings

router = APIRouter(prefix="/admin")

ROOT = Path(__file__).resolve().parents[3]
CALIBRATION_REPORT = ROOT / "docs" / "results" / "calibration.md"
CALIBRATION_LABELS = ROOT / "docs" / "results" / "calibration-labels.json"
MEASURE_SELECTION_REPORT = ROOT / "docs" / "results" / "measure-selection.md"
RETRIEVAL_ABLATION_REPORT = ROOT / "docs" / "results" / "retrieval-ablation.md"
LOG_FILE = ROOT / "logs" / "explorer.jsonl"

# Module-level so tests can monkeypatch each target independently rather than the whole module.


@router.get("/ingest-status")
def ingest_status() -> dict[str, Any]:
    """The latest run per source — not full history, which is what makes it readable at a
    glance instead of a table someone has to scroll."""
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (source)
                   source, rows_read, rows_upserted, duration_ms, sha256, status, detail,
                   started_at
              FROM ingest_runs
             ORDER BY source, started_at DESC
            """
        ).fetchall()

    runs = [
        {
            "source": r[0],
            "rows_read": r[1],
            "rows_upserted": r[2],
            "duration_ms": float(r[3]) if r[3] is not None else None,
            "sha256": r[4],
            "status": r[5],
            "detail": r[6],
            "started_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]
    return {"runs": runs}


@router.get("/calibration")
def calibration() -> dict[str, Any]:
    """The committed report, rendered as-is. The numbers in it are #28's, not recomputed here —
    recomputation would risk drifting from the file a reviewer actually reads."""
    if not CALIBRATION_REPORT.is_file():
        raise HTTPException(
            status_code=404,
            detail="No calibration report yet — run `python -m explorer.evals.calibration` "
            "(needs a key) and commit docs/results/calibration.md.",
        )
    return {"markdown": CALIBRATION_REPORT.read_text(encoding="utf-8")}


@router.get("/calibration-labels")
def calibration_labels() -> dict[str, Any]:
    """Accuracy per deal point before and after the Label tab's decisions (#41).

    Served from the committed artefact, not recomputed: recomputing on request would make the
    Admin table and the file in the repo two numbers that can disagree, and the whole point of
    the section is that a reviewer can check it against a command that ran.
    """
    if not CALIBRATION_LABELS.is_file():
        raise HTTPException(
            status_code=404,
            detail="No label-aware calibration yet — run "
            "`PYTHONPATH=backend python -m explorer.evals.calibration` and commit "
            "docs/results/calibration-labels.json.",
        )
    payload: dict[str, Any] = json.loads(CALIBRATION_LABELS.read_text(encoding="utf-8"))
    return payload


def git_sha() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            ).stdout.strip()
            or "unknown"
        )
    except Exception:  # noqa: BLE001 - git absent or not a repo; never fatal to the admin view
        return "unknown"


@router.get("/evals")
def evals() -> dict[str, Any]:
    """Latest eval reports, tagged with the commit they were produced against — a number with
    no SHA is unfalsifiable the moment the code changes again."""
    return {
        "git_sha": git_sha(),
        "measure_selection": (
            MEASURE_SELECTION_REPORT.read_text(encoding="utf-8")
            if MEASURE_SELECTION_REPORT.is_file()
            else None
        ),
        "retrieval_ablation": (
            RETRIEVAL_ABLATION_REPORT.read_text(encoding="utf-8")
            if RETRIEVAL_ABLATION_REPORT.is_file()
            else None
        ),
    }


def _redact_line(line: dict[str, Any]) -> dict[str, Any]:
    """Defense in depth: `logging.py`'s structlog processor already redacts at write time
    (D5), but the viewer must not trust that every line on disk went through it — an older
    file, a line written by a different process — so it redacts again here regardless."""
    return {k: (redact(v) if isinstance(v, str) else v) for k, v in line.items()}


@router.get("/logs")
def logs(
    level: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Tails and parses `logs/explorer.jsonl`. Paginated so a large file cannot lock up the
    viewer — measured at 87ms against the real 15,784-line file this session accumulated (see
    docs/worklog.md); reads the whole file into memory once per request rather than streaming,
    which is the ceiling on how large "does not lock up" actually holds."""
    if not LOG_FILE.is_file():
        return {"lines": [], "total_matched": 0}

    matched: list[dict[str, Any]] = []
    with LOG_FILE.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if level and line.get("level") != level:
                continue
            if q and q not in json.dumps(line):
                continue
            matched.append(line)

    page = matched[offset : offset + limit]
    return {
        "lines": [_redact_line(line) for line in page],
        "total_matched": len(matched),
        "offset": offset,
        "limit": limit,
    }

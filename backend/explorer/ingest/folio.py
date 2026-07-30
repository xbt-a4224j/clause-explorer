"""FOLIO ingest step: parse the OWL file and upsert it, recording the run (#6).

Runnable on its own (`PYTHONPATH=backend python -m explorer.ingest.folio`) and called by the
ingest CLI in #11. Re-running is a no-op on row counts.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import psycopg

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.folio.loader import parse_folio, upsert_concepts

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "folio" / "FOLIO.owl"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scalar(conn: psycopg.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


def run(path: Path | None = None, dsn: str | None = None) -> dict[str, object]:
    source_path = path or DEFAULT_PATH
    log = get_logger().bind(source="folio", file=str(source_path))
    started = time.perf_counter()

    if not source_path.exists():
        raise FileNotFoundError(
            f"{source_path} not found — see docs/provenance.md for the download command"
        )

    checksum = sha256_of(source_path)
    concepts = parse_folio(source_path)

    with psycopg.connect(dsn or settings.database_url) as conn:
        written = upsert_concepts(conn, concepts)
        total = _scalar(conn, "SELECT count(*) FROM folio_concepts")
        alias_total = _scalar(conn, "SELECT count(*) FROM folio_aliases")
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        conn.execute(
            "INSERT INTO ingest_runs (source, rows_read, rows_upserted, duration_ms, sha256, "
            "status, detail) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                "folio",
                len(concepts),
                written,
                duration_ms,
                checksum,
                "ok",
                f"{alias_total} aliases",
            ),
        )
        conn.commit()

    result = {
        "rows_read": len(concepts),
        "rows_upserted": written,
        "concepts_total": total,
        "aliases_total": alias_total,
        "duration_ms": duration_ms,
        "sha256": checksum,
    }
    log.info("ingest_folio", **result)
    return result


def main() -> None:
    configure_logging(settings.log_level, to_file=False)
    run()


if __name__ == "__main__":
    main()

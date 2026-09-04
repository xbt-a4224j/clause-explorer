"""One re-runnable entry point for every corpus (#11).

`python -m explorer.ingest --source {folio,maud,edgar,all}`

Order matters and is not alphabetical: FOLIO first because `matters.folio_industry_code` is a
foreign key into it, and MAUD before EDGAR because enrichment updates rows MAUD creates.

Every step is idempotent by natural key and every step writes an `ingest_runs` row, so the
Admin tab (#30) can show status without parsing the log file.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.ingest import edgar, folio, maud

# dependency order, not alphabetical — see module docstring
SOURCES: dict[str, Callable[..., dict[str, object]]] = {
    "folio": folio.run,
    "maud": maud.run,
    "edgar": edgar.run,
}


def run_source(source: str, dsn: str | None = None) -> dict[str, object]:
    """Run one step. Raises KeyError for an unknown source and FileNotFoundError — with the
    fixing command in the message — for a corpus that is not on disk."""
    step = SOURCES[source]
    return step(dsn=dsn) if dsn else step()


def run_all(sources: list[str], dsn: str | None = None) -> dict[str, dict[str, object]]:
    log = get_logger()
    results: dict[str, dict[str, object]] = {}
    started = time.perf_counter()
    for source in sources:
        results[source] = run_source(source, dsn=dsn)
    log.info(
        "ingest_complete",
        sources=sources,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m explorer.ingest")
    parser.add_argument(
        "--source",
        choices=[*SOURCES, "all"],
        default="all",
        help="which corpus to load; 'all' runs them in dependency order",
    )
    args = parser.parse_args(argv)

    configure_logging(settings.log_level, to_file=True)
    sources = list(SOURCES) if args.source == "all" else [args.source]

    try:
        run_all(sources)
    except FileNotFoundError as missing:
        # loudly, with the command that fixes it — never "loaded 0 rows, exit 0"
        print(f"ingest failed: {missing}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

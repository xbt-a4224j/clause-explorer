"""Schema application and teardown.

The schema itself is the platform's — `quorum/db/spine.sql` — and this module applies it plus
this domain's own `db/domain.sql`. That split is the point of the extraction: `records`, `facts`
and `categories` are what every corpus has, and `deal_value_usd` is what this one has.

`python -m explorer.db.migrate up|down|reset`, or `quorum migrate` for the same thing.
"""

from __future__ import annotations

import sys

import psycopg
from quorum.db import migrate as apply_spine

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.domain import ROOT

#: Drop order: dependents first, so foreign keys do not block teardown.
TABLES = [
    "facts",
    "labels",
    "selection_corrections",
    "ingest_runs",
    "records",
    "categories",
    "corpus_claim",
]


def up(dsn: str | None = None) -> None:
    with psycopg.connect(dsn or settings.database_url, autocommit=True) as conn:
        applied = apply_spine(conn, ROOT)
    get_logger().info("migrate_up", applied=applied, tables=len(TABLES))


def down(dsn: str | None = None) -> None:
    """Drop in dependency order so foreign keys do not block teardown."""
    with psycopg.connect(dsn or settings.database_url, autocommit=True) as conn:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    get_logger().info("migrate_down", tables=len(TABLES))


def reset(dsn: str | None = None) -> None:
    down(dsn)
    up(dsn)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "up"
    actions = {"up": up, "down": down, "reset": reset}
    if command not in actions:
        print(f"usage: python -m explorer.db.migrate [{'|'.join(actions)}]", file=sys.stderr)
        return 64
    actions[command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Schema application and teardown.

Plain SQL rather than Alembic: the schema is small, this is the only migration, and a
single readable .sql file is easier to review than a generated revision chain. If the
schema starts evolving across releases, swap this for Alembic then — not before.

`python -m explorer.db.migrate up|down|reset`
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings

SCHEMA = Path(__file__).with_name("schema.sql")

TABLES = [
    "deal_points",
    "labels",
    "ingest_runs",
    "matters",
    "folio_aliases",
    "folio_concepts",
]


def up(dsn: str | None = None) -> None:
    with psycopg.connect(dsn or settings.database_url, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
    get_logger().info("migrate_up", tables=len(TABLES))


def down(dsn: str | None = None) -> None:
    """Drop in dependency order so foreign keys do not block teardown."""
    with psycopg.connect(dsn or settings.database_url, autocommit=True) as conn:
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.execute("DROP FUNCTION IF EXISTS touch_updated_at() CASCADE")
    get_logger().info("migrate_down", tables=len(TABLES))


def main() -> None:
    configure_logging(settings.log_level, to_file=False)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "up"
    if cmd == "up":
        up()
    elif cmd == "down":
        down()
    elif cmd == "reset":
        down()
        up()
    else:
        print(f"unknown command: {cmd} (expected up|down|reset)", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()

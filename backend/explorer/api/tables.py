"""`GET /tables/*` — raw rows, read by the app rather than browsed by a person.

#31 built this so nobody had to open psql, behind a Tables tab. #48 cut that tab: browsing raw
rows is a convenience for whoever operates the thing, not a feature for a lawyer. The routes
stay because Admin reads ingest status and the Overview corpus strip reads its counts through
them. `/{table}/export.csv` went with the tab — the Tables view was its only caller.

Every query here is built from a whitelist, never from the caller's string. The table name and
every sortable/filterable column are checked against `information_schema` at import-adjacent
time; a name that isn't in that set never reaches SQL. This is the one place in the app that
exists specifically to expose raw rows, so it is also the one place a naive implementation would
most easily become an injection point.

**No limit above the ceiling, ever, silently or otherwise.** The AC is "the frontend never
loads a whole table" — capping an over-large request instead of rejecting it would let a caller
believe it received everything when it did not, which is a worse failure than a 422.
"""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query

from explorer.api.settings import settings

router = APIRouter(prefix="/tables")

# Every browsable table, explicitly. Not "every table in the schema" — ingest metadata like
# schema_migrations has no reason to be browsable here.
ALLOWED_TABLES = {
    "matters",
    "deal_points",
    "industries",
    "labels",
    "ingest_runs",
}

MAX_LIMIT = 500


def _require_table(table: str) -> str:
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=404, detail=f"No browsable table {table!r}.")
    return table


def _columns(conn: psycopg.Connection[Any], table: str) -> list[tuple[str, str]]:
    # Always plain tuples, regardless of the connection's row_factory (callers with dict_row
    # would otherwise break on positional indexing here).
    with conn.cursor(row_factory=psycopg.rows.tuple_row) as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
            (table,),
        )
        rows = cur.fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _require_column(conn: psycopg.Connection[Any], table: str, column: str) -> str:
    known = {name for name, _ in _columns(conn, table)}
    if column not in known:
        raise HTTPException(status_code=422, detail=f"{column!r} is not a column of {table!r}.")
    return column


def _pk(table: str) -> str:
    return "id"


@router.get("/{table}/schema")
def schema(table: str) -> dict[str, Any]:
    _require_table(table)
    with psycopg.connect(settings.database_url) as conn:
        cols = _columns(conn, table)
        row_count_row = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
        row_count = row_count_row[0] if row_count_row else 0

        columns = []
        for name, data_type in cols:
            null_count_row = conn.execute(
                f'SELECT count(*) FROM "{table}" WHERE "{name}" IS NULL'
            ).fetchone()
            columns.append(
                {
                    "name": name,
                    "type": data_type,
                    "null_count": null_count_row[0] if null_count_row else 0,
                    # Same naming convention as the matter card (#20): is_inferred_* columns
                    # are read generically, not hardcoded per table, so a new one is flagged
                    # automatically.
                    "is_inferred_flag": name.startswith("is_inferred"),
                }
            )
    return {"table": table, "row_count": row_count, "columns": columns}


def _build_query(
    conn: psycopg.Connection[Any],
    table: str,
    sort: str | None,
    direction: str,
    filter_column: str | None,
    filter_value: str | None,
) -> tuple[str, str, list[Any]]:
    """Returns (where_sql, order_sql, params) — every identifier already validated against the
    whitelist, every value bound as a parameter, never interpolated."""
    where_sql = ""
    params: list[Any] = []
    if filter_column and filter_value is not None:
        _require_column(conn, table, filter_column)
        where_sql = f' WHERE "{filter_column}"::text ILIKE %s'
        params.append(f"%{filter_value}%")

    order_sql = ""
    if sort:
        _require_column(conn, table, sort)
        dir_sql = "DESC" if direction.lower() == "desc" else "ASC"
        order_sql = f' ORDER BY "{sort}" {dir_sql}'
    return where_sql, order_sql, params


@router.get("/{table}/rows")
def rows(
    table: str,
    sort: str | None = Query(default=None),
    dir: str = Query(default="asc"),
    filter_column: str | None = Query(default=None),
    filter_value: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    _require_table(table)
    with psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row) as conn:
        where_sql, order_sql, params = _build_query(
            conn, table, sort, dir, filter_column, filter_value
        )
        total = conn.execute(
            f'SELECT count(*) AS n FROM "{table}"{where_sql}',
            params,
        ).fetchone()
        page = conn.execute(
            f'SELECT * FROM "{table}"{where_sql}{order_sql} LIMIT %s OFFSET %s',
            [*params, limit, offset],
        ).fetchall()
    return {
        "table": table,
        "total_count": total["n"] if total else 0,
        "rows": [_serialize(r) for r in page],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{table}/rows/{row_id}")
def row_detail(table: str, row_id: str) -> dict[str, Any]:
    _require_table(table)
    pk = _pk(table)
    with psycopg.connect(settings.database_url, row_factory=psycopg.rows.dict_row) as conn:
        row = conn.execute(
            f'SELECT * FROM "{table}" WHERE "{pk}"::text = %s',
            (row_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No row {row_id!r} in {table!r}.")
    return _serialize(row)


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}

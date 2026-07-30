"""Text -> FOLIO code, and hierarchy walks over the denormalized ancestry.

`resolve()` is deliberately exact-then-alias-then-None. No fuzzy matching here: a wrong code
returns rows about the wrong industry, which looks exactly like a right answer. Embedding
nearest-neighbour resolution belongs to #25, where it is paired with an explicit "did you
mean" refusal rather than a silent substitution.
"""

from __future__ import annotations

from psycopg import Connection


def resolve(conn: Connection, text: str) -> str | None:
    """Exact label (case/whitespace-insensitive), then unique alias, then None."""
    needle = text.strip().lower()
    if not needle:
        return None

    row = conn.execute(
        "SELECT code FROM folio_concepts WHERE lower(label) = %s ORDER BY code LIMIT 1",
        (needle,),
    ).fetchone()
    if row is not None:
        return str(row[0])

    rows = conn.execute(
        "SELECT DISTINCT code FROM folio_aliases WHERE lower(alias) = %s LIMIT 2",
        (needle,),
    ).fetchall()
    if len(rows) == 1:
        return str(rows[0][0])
    # zero matches, or an ambiguous alias: None rather than a coin flip
    return None


def ancestors(conn: Connection, code: str) -> list[str]:
    """Root-first ancestor codes, excluding `code` itself."""
    row = conn.execute(
        "SELECT level_1_code, level_2_code, level_3_code, level "
        "FROM folio_concepts WHERE code = %s",
        (code,),
    ).fetchone()
    if row is None:
        return []
    chain = [c for c in row[:3] if c is not None]
    if row[3] > 4:
        # deeper than the denormalized columns reach; walk parents for the tail
        chain = _walk_up(conn, code)
    return [c for c in chain if c != code]


def _walk_up(conn: Connection, code: str) -> list[str]:
    chain: list[str] = []
    current: str | None = code
    seen = {code}
    while current is not None:
        row = conn.execute(
            "SELECT parent_code FROM folio_concepts WHERE code = %s", (current,)
        ).fetchone()
        current = row[0] if row and row[0] and row[0] not in seen else None
        if current is not None:
            seen.add(current)
            chain.append(current)
    chain.reverse()
    return chain


def descendants(conn: Connection, code: str) -> list[str]:
    """All codes below `code`, any depth. Recursive CTE is fine here — this is a drill-down
    on demand, not a per-facet-query cost inside Cube."""
    rows = conn.execute(
        """
        WITH RECURSIVE sub AS (
            SELECT code FROM folio_concepts WHERE parent_code = %s
            UNION ALL
            SELECT f.code FROM folio_concepts f JOIN sub ON f.parent_code = sub.code
        )
        SELECT code FROM sub
        """,
        (code,),
    ).fetchall()
    return [str(r[0]) for r in rows]

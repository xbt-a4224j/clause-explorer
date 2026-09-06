"""Which corpus this database holds, and a refusal to write into somebody else's.

A fork of this repo, pointed at a different domain, published Postgres on the same 5432 and
used the same database name. Its ingest wrote 979 matters and 19,580 deal-point rows of
healthcare claims data into the merger-agreement corpus. Nothing errored. Nothing was
overwritten. The two corpora simply interleaved, and the app started reporting 1,131 matters
with an industry rail reading "Injury — sprain or strain  n=254".

The rows were the cheap part — a `DELETE` fixed those. The expensive part was that every
published figure silently became wrong, and the only reason anyone noticed was a deal-point
count of 112 where the README said 92.

**Idempotency is what made it quiet.** An ingest keyed on its own `matter_id`s has no reason to
look at rows it did not write, so it never notices it is a guest in another project's database.
The property that makes re-running safe is exactly the property that makes this invisible.

So the check cannot be "do the rows look like mine". It has to be an explicit claim: the first
ingest stamps its name, and every later ingest reads that stamp before touching anything.
"""

from __future__ import annotations

import psycopg

#: The name this project stamps. A fork changes this line and nothing else — that is the whole
#: interface. Deliberately not derived from the database name or the DSN, because those are the
#: things that collided in the first place.
CORPUS_NAME = "maud-public-target-merger-agreements"

CLAIM_TABLE = """
CREATE TABLE IF NOT EXISTS corpus_claim (
    name            text        PRIMARY KEY,
    first_ingest_at timestamptz NOT NULL DEFAULT clock_timestamp()
)
"""


class ForeignCorpus(RuntimeError):
    """Raised when the database already belongs to a different project."""


def claim_corpus(conn: psycopg.Connection, name: str | None = None) -> str:
    """Assert this database is ours, claiming it if nobody has.

    Returns the claimed name. Raises `ForeignCorpus` — before any write — when the stamp
    belongs to someone else.

    Idempotent by design: ingest is re-run constantly and the guard must never be the thing
    that breaks the second run.
    """
    corpus = name or CORPUS_NAME
    conn.execute(CLAIM_TABLE)
    row = conn.execute("SELECT name FROM corpus_claim LIMIT 1").fetchone()

    if row is None:
        conn.execute("INSERT INTO corpus_claim (name) VALUES (%s)", (corpus,))
        conn.commit()
        return corpus

    existing = str(row[0])
    if existing != corpus:
        raise ForeignCorpus(
            f"This database already holds the {existing!r} corpus, and this ingest writes "
            f"{corpus!r}. Two corpora in one database do not collide loudly — they "
            f"interleave, and every count, facet and published figure silently becomes a "
            f"number about both. Point this project at its own database, e.g. "
            f"CLAUSE_EXPLORER_DB=postgresql://explorer:explorer@localhost:5432/"
            f"{corpus.split('-')[0]}_explorer, or publish Postgres on a different port. "
            f"Nothing has been written."
        )
    return existing

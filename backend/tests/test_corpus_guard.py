"""The ingest must refuse to write into another project's corpus.

This is not hypothetical. A fork of this repo pointed at a different domain published Postgres
on the same 5432 and used the same database name, so its `make ingest` wrote 979 matters and
19,580 deal-point rows of healthcare CLAIMS data into the merger-agreement corpus. Nothing
errored. Nothing overwrote. The two corpora simply interleaved, and the app began reporting
1,131 matters with an industry rail reading "Injury — sprain or strain n=254".

The damage was not the rows; the rows were deletable. The damage was that every published
figure silently became wrong, and the only reason it was caught was someone noticing a deal
point count of 112 where the README said 92.

Idempotency by matter_id is exactly what made it quiet: an ingest keyed on its own ids has no
reason to look at rows it did not write, so it never notices it is a guest in someone else's
database.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.ingest.corpus import CORPUS_NAME, ForeignCorpus, claim_corpus

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _db_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="postgres not running")


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        c.execute("DROP TABLE IF EXISTS corpus_claim")
        c.commit()
        yield c
        c.execute("DROP TABLE IF EXISTS corpus_claim")
        c.commit()


@needs_db
class TestClaimingAnEmptyDatabase:
    def test_the_first_ingest_claims_it(self, conn) -> None:
        claim_corpus(conn)
        row = conn.execute("SELECT name FROM corpus_claim").fetchone()
        assert row[0] == CORPUS_NAME

    def test_claiming_twice_is_fine(self, conn) -> None:
        """Ingest is idempotent and gets re-run constantly; the guard must not be the thing
        that breaks the second run."""
        claim_corpus(conn)
        claim_corpus(conn)
        assert conn.execute("SELECT count(*) FROM corpus_claim").fetchone()[0] == 1


@needs_db
class TestRefusingSomeoneElsesDatabase:
    def test_a_foreign_corpus_stops_the_ingest(self, conn) -> None:
        claim_corpus(conn, name="claims-explorer")
        with pytest.raises(ForeignCorpus):
            claim_corpus(conn)

    def test_the_error_names_both_corpora_and_the_fix(self, conn) -> None:
        """A guard that says only "no" sends someone hunting. This one has to say whose
        database it is and what to change, because the person hitting it is running a fork and
        does not yet know the two share a DSN."""
        claim_corpus(conn, name="claims-explorer")
        with pytest.raises(ForeignCorpus) as excinfo:
            claim_corpus(conn)
        message = str(excinfo.value)
        assert "claims-explorer" in message
        assert CORPUS_NAME in message
        assert "CLAUSE_EXPLORER_DB" in message

    def test_it_refuses_before_writing_anything(self, conn) -> None:
        """The whole point is to stop ahead of the write. A guard that reports the collision
        after 19,580 rows have landed has documented the accident, not prevented it."""
        claim_corpus(conn, name="claims-explorer")
        before = conn.execute("SELECT count(*) FROM matters").fetchone()[0]
        with pytest.raises(ForeignCorpus):
            claim_corpus(conn)
        assert conn.execute("SELECT count(*) FROM matters").fetchone()[0] == before

"""The ingest CLI and its idempotency contract (#11).

The load-bearing assertion is not "row counts are stable" — it is that a second run does not
bump `updated_at` on rows whose content did not change. Cube's `refresh_key` is
`SELECT MAX(updated_at)` (#14), so an unconditional `DO UPDATE SET` makes every re-ingest
look like new data and invalidates every cached aggregate for nothing.

These tests are slow (they run the real corpora) and skip when a corpus is absent.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.ingest.cli import SOURCES, run_source
from explorer.ingest.maud_corpus import corpus_available as maud_available

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

TABLES = ("industries", "matters", "deal_points")


def _db_available() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_everything = pytest.mark.skipif(
    not (_db_available() and maud_available()),
    reason="needs Postgres plus the MAUD corpus",
)


def _snapshot(conn) -> dict[str, tuple[int, object]]:
    return {
        table: conn.execute(f"SELECT count(*), max(updated_at) FROM {table}").fetchone()
        for table in TABLES
    }


class TestSources:
    def test_every_source_is_addressable(self) -> None:
        assert set(SOURCES) == {"maud", "edgar"}

    def test_folio_is_no_longer_a_source(self) -> None:
        """#49: the ontology load is gone; the industry vocabulary is seeded by the EDGAR
        step from the checked-in crosswalk it already reads."""
        assert "folio" not in SOURCES
        with pytest.raises(KeyError):
            run_source("folio")

    def test_cuad_is_no_longer_a_source(self) -> None:
        """#40: a corpus no endpoint queries is an ingest path to maintain for nothing."""
        assert "cuad" not in SOURCES
        with pytest.raises(KeyError):
            run_source("cuad")

    def test_unknown_source_is_rejected(self) -> None:
        with pytest.raises(KeyError):
            run_source("sec-full-text")


@needs_everything
class TestIdempotency:
    @pytest.fixture(scope="class")
    def first_pass(self):
        for source in SOURCES:
            run_source(source)
        with psycopg.connect(DSN) as conn:
            return _snapshot(conn)

    def test_row_counts_are_stable_across_runs(self, first_pass) -> None:
        for source in SOURCES:
            run_source(source)
        with psycopg.connect(DSN) as conn:
            second = _snapshot(conn)
        assert {t: v[0] for t, v in second.items()} == {t: v[0] for t, v in first_pass.items()}

    def test_updated_at_does_not_move_when_nothing_changed(self, first_pass) -> None:
        """The Cube refresh_key contract. An unconditional upsert fails this."""
        for source in SOURCES:
            run_source(source)
        with psycopg.connect(DSN) as conn:
            second = _snapshot(conn)
        for table in TABLES:
            assert second[table][1] == first_pass[table][1], (
                f"{table} touched rows it did not change"
            )

    def test_a_real_change_does_move_updated_at(self, first_pass) -> None:
        """The other half: the guard must not be so tight that genuine edits go unnoticed."""
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "UPDATE deal_points SET position = position || ' (edited)' "
                "WHERE id = (SELECT min(id) FROM deal_points)"
            )
            conn.commit()
            touched = conn.execute("SELECT max(updated_at) FROM deal_points").fetchone()[0]
        assert touched > first_pass["deal_points"][1]

        run_source("maud")  # restores the row from the corpus
        with psycopg.connect(DSN) as conn:
            restored = conn.execute("SELECT max(updated_at) FROM deal_points").fetchone()[0]
        assert restored > touched


@needs_everything
class TestRunTracking:
    def test_each_run_writes_an_ingest_runs_row(self) -> None:
        with psycopg.connect(DSN) as conn:
            before = conn.execute("SELECT count(*) FROM ingest_runs").fetchone()[0]
        run_source("edgar")
        with psycopg.connect(DSN) as conn:
            row = conn.execute(
                "SELECT source, rows_read, rows_upserted, duration_ms, status "
                "FROM ingest_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            after = conn.execute("SELECT count(*) FROM ingest_runs").fetchone()[0]
        assert after == before + 1
        assert row[0] == "edgar"
        assert row[1] > 0 and row[2] > 0 and row[3] > 0
        assert row[4] == "ok"


class TestMissingCorpusFailsLoudly:
    def test_missing_corpus_raises_with_the_fixing_command(self, monkeypatch) -> None:
        """Never silently load nothing: the message has to name the script that fixes it."""
        from explorer.ingest import maud_corpus

        monkeypatch.setattr(maud_corpus, "corpus_available", lambda: False)
        with pytest.raises(FileNotFoundError, match="download_maud.sh"):
            run_source("maud")

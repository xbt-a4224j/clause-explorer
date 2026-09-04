"""Schema contract.

The single most consequential shape decision in the project is that `deal_points` is LONG
(one row per matter × deal point) rather than wide (one column per deal point). MAUD ships
92 deal points; wide would make every additional one a three-place change — migration, Cube
model, UI. Long makes it rows.

These tests run against a real Postgres, so they are skipped when one is unreachable rather
than failing CI on an environment problem.
"""

from __future__ import annotations

import os

import psycopg
import pytest

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _db_available() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 - availability probe; any failure means skip
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        yield c


def _columns(conn, table: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = %s",
        (table,),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


class TestTablesExist:
    @pytest.mark.parametrize(
        "table",
        ["matters", "deal_points", "folio_concepts", "labels", "ingest_runs"],
    )
    def test_table_exists(self, conn, table: str) -> None:
        assert _columns(conn, table), f"{table} is missing"

    def test_clauses_is_gone(self, conn) -> None:
        """#40 dropped CUAD, the only corpus that ever wrote `clauses`.

        The table has to actually disappear from an already-migrated database, not just
        stop being written: an empty table left behind is still a Tables-view row, a
        refresh_key target, and a thing to explain.
        """
        assert not _columns(conn, "clauses"), (
            "clauses still exists; migrate up did not drop the CUAD-only table"
        )


class TestDealPointsIsLong:
    """The extensibility invariant. If these fail, adding a deal point becomes a migration."""

    def test_has_a_deal_point_name_column(self, conn) -> None:
        assert "deal_point_name" in _columns(conn, "deal_points")

    def test_has_no_per_deal_point_columns(self, conn) -> None:
        """A wide schema would show up as columns named after specific deal points."""
        cols = set(_columns(conn, "deal_points"))
        wide_smells = {"fiduciary_out", "ticking_fee", "go_shop", "has_fiduciary_exception"}
        assert not (cols & wide_smells), f"wide-shaped columns present: {cols & wide_smells}"

    def test_a_new_deal_point_needs_no_schema_change(self, conn) -> None:
        """Insert a deal point name that has never been seen; it must just be a row."""
        conn.execute(
            "INSERT INTO matters (id, source_file, source_contract_title) "
            "VALUES ('t-long', 'test.txt', 'Test') ON CONFLICT (id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO deal_points (matter_id, deal_point_name, position) "
            "VALUES ('t-long', 'A Deal Point Invented By This Test', 'present') "
            "ON CONFLICT (matter_id, deal_point_name) DO NOTHING"
        )
        got = conn.execute(
            "SELECT position FROM deal_points WHERE matter_id='t-long' "
            "AND deal_point_name='A Deal Point Invented By This Test'"
        ).fetchone()
        assert got is not None and got[0] == "present"
        conn.execute("DELETE FROM deal_points WHERE matter_id='t-long'")
        conn.execute("DELETE FROM matters WHERE id='t-long'")


class TestProvenanceAndInference:
    def test_matters_carry_provenance(self, conn) -> None:
        cols = _columns(conn, "matters")
        assert {"source_file", "source_contract_title"} <= set(cols)

    def test_inferred_fields_are_flagged(self, conn) -> None:
        """FOLIO industry codes are classifier output, not ground truth. The schema says so."""
        cols = set(_columns(conn, "matters"))
        assert any(c.startswith("is_inferred") for c in cols), (
            "no is_inferred_* column on matters; inferred data would be indistinguishable "
            "from gold labels"
        )


class TestUpdatedAt:
    """Cube's refresh_key (#14) is SELECT MAX(updated_at); every table needs one."""

    @pytest.mark.parametrize("table", ["matters", "deal_points", "folio_concepts", "labels"])
    def test_has_updated_at(self, conn, table: str) -> None:
        assert "updated_at" in _columns(conn, table)

    def test_updated_at_advances_on_write(self, conn) -> None:
        conn.execute(
            "INSERT INTO matters (id, source_file, source_contract_title) "
            "VALUES ('t-touch', 'test.txt', 'Test') ON CONFLICT (id) DO NOTHING"
        )
        before = conn.execute("SELECT updated_at FROM matters WHERE id='t-touch'").fetchone()[0]
        conn.execute("UPDATE matters SET source_contract_title='Changed' WHERE id='t-touch'")
        after = conn.execute("SELECT updated_at FROM matters WHERE id='t-touch'").fetchone()[0]
        assert after > before, "updated_at did not advance; Cube refresh_key would go stale"
        conn.execute("DELETE FROM matters WHERE id='t-touch'")

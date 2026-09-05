"""The `industries` table and its seed (#49).

This replaces `test_folio.py`, deleted with the ontology it tested. What is being asserted
here is the *one property* the ontology was earning: a filter joins on a stable **code**, not
on a display label. A label that drifts from "Health Care Industry" to "Healthcare" must not
silently return zero rows, because zero rows reads as "we have no comparable deals".

The seed is the checked-in crosswalk, so these tests need no ontology file and no network —
`data/mappings/sic_to_folio.csv` is committed on purpose.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.ingest.edgar import SicIndustryMap, industry_rows, seed_industries

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _db_available() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 - availability probe; any failure means skip
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        yield c


class TestIndustryRows:
    """The crosswalk is many SIC prefixes to one industry; the table is one row per industry."""

    def test_one_row_per_distinct_code(self) -> None:
        rows = industry_rows(SicIndustryMap.load())
        codes = [code for code, _ in rows]
        assert len(codes) == len(set(codes)), "duplicate code would break the primary key"

    def test_codes_carry_the_label_a_partner_reads(self) -> None:
        labels = dict(industry_rows(SicIndustryMap.load()))
        assert labels["RCSG4k3ah1Pu5YgPexPgOmL"] == "Health Care Industry"

    def test_labels_with_a_comma_survive_csv_quoting(self) -> None:
        """Two labels contain a comma. Splitting on `,` instead of parsing CSV truncates them
        to "Real Estate" and "Arts", which then never match anything the corpus carries."""
        labels = set(dict(industry_rows(SicIndustryMap.load())).values())
        assert "Real Estate, Rental and Leasing Industry" in labels

    def test_every_resolvable_code_has_a_row(self) -> None:
        """A matter can only be given a code the crosswalk resolves to; the table must hold
        every one of them or the foreign key rejects the enrichment."""
        mapping = SicIndustryMap.load()
        seeded = {code for code, _ in industry_rows(mapping)}
        assert set(mapping.rows.values()) <= seeded


@needs_db
class TestSeed:
    def test_seed_is_idempotent(self, conn) -> None:
        expected = len(industry_rows(SicIndustryMap.load()))
        seed_industries(conn)
        first = conn.execute("SELECT count(*) FROM industries").fetchone()[0]
        seed_industries(conn)
        second = conn.execute("SELECT count(*) FROM industries").fetchone()[0]
        assert first == second == expected

    def test_matters_join_on_the_code_not_the_label(self, conn) -> None:
        """The property the ontology was carrying, kept: the join key is opaque and stable."""
        seed_industries(conn)
        row = conn.execute(
            "SELECT i.label FROM industries i WHERE i.code = %s",
            ("RCSG4k3ah1Pu5YgPexPgOmL",),
        ).fetchone()
        assert row is not None and row[0] == "Health Care Industry"

    def test_a_drifted_label_resolves_to_nothing_while_the_code_still_does(self, conn) -> None:
        """The failure this design prevents, asserted directly rather than described."""
        seed_industries(conn)
        by_label = conn.execute(
            "SELECT count(*) FROM industries WHERE label = %s", ("Healthcare",)
        ).fetchone()[0]
        by_code = conn.execute(
            "SELECT count(*) FROM industries WHERE code = %s", ("RCSG4k3ah1Pu5YgPexPgOmL",)
        ).fetchone()[0]
        assert (by_label, by_code) == (0, 1)


@needs_db
class TestOntologyIsGone:
    """#49: the tables the ontology needed have to actually disappear from an already-migrated
    database, the way `clauses` did in #40. A table left behind is still a Tables-view row, a
    refresh_key target, and a thing to explain."""

    @pytest.mark.parametrize("table", ["folio_concepts", "folio_aliases"])
    def test_table_is_dropped(self, conn, table: str) -> None:
        exists = conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchone()[0]
        assert exists == 0, f"{table} still exists; migrate up did not drop it"

    def test_matters_industry_column_is_renamed(self, conn) -> None:
        cols = {
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'matters'"
            )
        }
        assert "industry_code" in cols
        assert "folio_industry_code" not in cols

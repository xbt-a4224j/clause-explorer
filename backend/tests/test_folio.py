"""FOLIO ontology load and lookup (#6).

Two kinds of test here, deliberately:

* Parser tests run against a small hand-written OWL fixture. The real file is 18 MB and
  takes ~3 s to parse; putting the hierarchy logic under a fixture keeps the feedback loop
  fast and makes the expected tree readable in the test itself.
* One test parses the real `data/folio/FOLIO.owl` and hand-checks a branch
  (Industry and Market -> Industry -> Health Care Industry -> Hospitals Industry). Fixtures
  cannot catch "the ontology is not shaped the way we assumed"; only the real file can.

DB tests use fixture codes prefixed `TEST_` so they never collide with loaded FOLIO rows.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from explorer.folio.loader import Concept, parse_folio, upsert_concepts
from explorer.folio.resolve import ancestors, descendants, resolve

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")
FOLIO_FILE = Path(__file__).resolve().parents[2] / "data" / "folio" / "FOLIO.owl"

FIXTURE_OWL = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#"
         xml:base="https://folio.openlegalstandard.org/">
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_ROOT">
    <rdfs:subClassOf rdf:resource="http://www.w3.org/2002/07/owl#Thing"/>
    <rdfs:label>Test Industry and Market</rdfs:label>
  </owl:Class>
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_MID">
    <rdfs:subClassOf rdf:resource="https://folio.openlegalstandard.org/TEST_ROOT"/>
    <rdfs:label>Test Industry</rdfs:label>
  </owl:Class>
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_LEAF">
    <rdfs:subClassOf rdf:resource="https://folio.openlegalstandard.org/TEST_MID"/>
    <rdfs:label>Test Health Care Industry</rdfs:label>
    <skos:definition>Establishments providing health care.</skos:definition>
    <skos:altLabel>Test Healthcare</skos:altLabel>
    <skos:altLabel>Test Health Care Industry</skos:altLabel>
  </owl:Class>
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_DEEP">
    <rdfs:subClassOf rdf:resource="https://folio.openlegalstandard.org/TEST_LEAF"/>
    <rdfs:label>Test Hospitals Industry</rdfs:label>
  </owl:Class>
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_DEPRECATED">
    <rdfs:label>DEPRECATED Test Things</rdfs:label>
  </owl:Class>
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_DEPRECATED_CHILD">
    <rdfs:subClassOf rdf:resource="https://folio.openlegalstandard.org/TEST_DEPRECATED"/>
    <rdfs:label>Test Obsolete Thing</rdfs:label>
  </owl:Class>
  <owl:Class rdf:about="https://folio.openlegalstandard.org/TEST_UNLABELLED">
    <rdfs:subClassOf rdf:resource="https://folio.openlegalstandard.org/TEST_ROOT"/>
  </owl:Class>
</rdf:RDF>
"""


@pytest.fixture(scope="module")
def fixture_concepts(tmp_path_factory) -> list[Concept]:
    path = tmp_path_factory.mktemp("folio") / "fixture.owl"
    path.write_text(FIXTURE_OWL)
    return parse_folio(path)


@pytest.fixture(scope="module")
def by_code(fixture_concepts: list[Concept]) -> dict[str, Concept]:
    return {c.code: c for c in fixture_concepts}


class TestParse:
    def test_codes_are_the_iri_suffix(self, by_code: dict[str, Concept]) -> None:
        assert "TEST_LEAF" in by_code

    def test_parent_and_level(self, by_code: dict[str, Concept]) -> None:
        assert by_code["TEST_ROOT"].parent_code is None
        assert by_code["TEST_ROOT"].level == 1
        assert by_code["TEST_MID"].parent_code == "TEST_ROOT"
        assert by_code["TEST_MID"].level == 2
        assert by_code["TEST_DEEP"].level == 4

    def test_denormalized_ancestry(self, by_code: dict[str, Concept]) -> None:
        """Cube reads these three columns instead of walking a recursive CTE per facet."""
        deep = by_code["TEST_DEEP"]
        assert (deep.level_1_code, deep.level_2_code, deep.level_3_code) == (
            "TEST_ROOT",
            "TEST_MID",
            "TEST_LEAF",
        )
        root = by_code["TEST_ROOT"]
        assert (root.level_1_code, root.level_2_code, root.level_3_code) == (
            "TEST_ROOT",
            None,
            None,
        )

    def test_definition_and_aliases(self, by_code: dict[str, Concept]) -> None:
        leaf = by_code["TEST_LEAF"]
        assert leaf.definition is not None and leaf.definition.startswith("Establishments")
        assert "Test Healthcare" in leaf.aliases

    def test_alias_identical_to_label_is_dropped(self, by_code: dict[str, Concept]) -> None:
        assert "Test Health Care Industry" not in by_code["TEST_LEAF"].aliases

    def test_deprecated_subtree_excluded(self, by_code: dict[str, Concept]) -> None:
        """DEPRECATED and SANDBOX branches would pollute resolve() with dead vocabulary."""
        assert "TEST_DEPRECATED" not in by_code
        assert "TEST_DEPRECATED_CHILD" not in by_code

    def test_unlabelled_class_excluded(self, by_code: dict[str, Concept]) -> None:
        assert "TEST_UNLABELLED" not in by_code


def _db_available() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2):
            return True
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@pytest.fixture
def conn():
    with psycopg.connect(DSN) as c:
        yield c
        c.execute("DELETE FROM folio_concepts WHERE code LIKE 'TEST\\_%'")
        c.commit()


@needs_db
class TestUpsert:
    def test_rows_land_with_hierarchy(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        row = conn.execute(
            "SELECT label, parent_code, level, level_1_code, level_3_code "
            "FROM folio_concepts WHERE code = 'TEST_DEEP'"
        ).fetchone()
        assert row == ("Test Hospitals Industry", "TEST_LEAF", 4, "TEST_ROOT", "TEST_LEAF")

    def test_idempotent(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        before = conn.execute("SELECT count(*) FROM folio_concepts").fetchone()[0]
        alias_before = conn.execute("SELECT count(*) FROM folio_aliases").fetchone()[0]
        upsert_concepts(conn, fixture_concepts)
        after = conn.execute("SELECT count(*) FROM folio_concepts").fetchone()[0]
        alias_after = conn.execute("SELECT count(*) FROM folio_aliases").fetchone()[0]
        assert (after, alias_after) == (before, alias_before)


@needs_db
class TestResolve:
    """Exact label, then alias, then None. No fuzzy matching in this issue (#6) —
    embedding-nearest resolution is #25, and doing it here would hide misses."""

    def test_exact_label(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert resolve(conn, "Test Health Care Industry") == "TEST_LEAF"

    def test_case_and_whitespace_insensitive(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert resolve(conn, "  test health care industry ") == "TEST_LEAF"

    def test_alias(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert resolve(conn, "Test Healthcare") == "TEST_LEAF"

    def test_unknown_is_none_not_a_guess(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert resolve(conn, "Test Health Car") is None
        assert resolve(conn, "") is None


@needs_db
class TestHierarchyQueries:
    def test_ancestors_root_first(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert ancestors(conn, "TEST_DEEP") == ["TEST_ROOT", "TEST_MID", "TEST_LEAF"]

    def test_ancestors_of_a_root_is_empty(self, conn, fixture_concepts: list[Concept]) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert ancestors(conn, "TEST_ROOT") == []

    def test_descendants_includes_all_levels_below(
        self, conn, fixture_concepts: list[Concept]
    ) -> None:
        upsert_concepts(conn, fixture_concepts)
        assert set(descendants(conn, "TEST_ROOT")) == {"TEST_MID", "TEST_LEAF", "TEST_DEEP"}


@pytest.mark.skipif(not FOLIO_FILE.exists(), reason="FOLIO.owl not downloaded")
class TestRealOntology:
    """Hand-checked against the published ontology:
    Industry and Market -> Industry -> Health Care Industry -> Hospitals Industry."""

    @pytest.fixture(scope="class")
    def real(self) -> dict[str, Concept]:
        return {c.code: c for c in parse_folio(FOLIO_FILE)}

    def test_loads_the_bulk_of_the_ontology(self, real: dict[str, Concept]) -> None:
        assert len(real) > 15_000

    def test_healthcare_branch_shape(self, real: dict[str, Concept]) -> None:
        hospitals = real["REDA36d2F98543EBb23B69ba"]
        assert hospitals.label == "Hospitals Industry"
        assert hospitals.parent_code == "RCSG4k3ah1Pu5YgPexPgOmL"  # Health Care Industry
        assert hospitals.level == 4
        assert hospitals.level_1_code == "R8f4qGdjxuiQary8OBpq8W9"  # Industry and Market
        assert hospitals.level_2_code == "RDIwFaFcH4KY0gwEY0QlMTp"  # Industry
        assert hospitals.level_3_code == "RCSG4k3ah1Pu5YgPexPgOmL"

    def test_every_concept_has_a_level_1(self, real: dict[str, Concept]) -> None:
        assert [c.code for c in real.values() if c.level_1_code is None] == []

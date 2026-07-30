"""CUAD -> clauses (#10).

CUAD is the easy provenance case and the hard honesty case.

Easy: it ships SQuAD-style `answer_start` offsets into the contract text it also ships, so
char ranges are read, not reconstructed. Contrast #8, where MAUD's excerpts had to be
anchored back into the source.

Hard: CUAD carries **no industry metadata at all**. Any FOLIO industry on these rows is
classifier output, which is why `is_inferred_industry` defaults TRUE on the table and why the
tests below assert no row can claim otherwise.
"""

from __future__ import annotations

import json
import os
import random

import psycopg
import pytest
from explorer.ingest.cuad import (
    CUAD_FILE,
    clause_id,
    corpus_available,
    parse_cuad,
    upsert_clauses,
)

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

needs_corpus = pytest.mark.skipif(
    not corpus_available(), reason="CUAD not downloaded — run scripts/download_cuad.sh"
)

CONTEXT = (
    "EXHIBIT 10 DISTRIBUTOR AGREEMENT between Acme and Beta. "
    "This Agreement shall be governed by the laws of Delaware."
)

FIXTURE = {
    "version": "aok_v1.0",
    "data": [
        {
            "title": "ACMECO_01_01_2020-EX-10-DISTRIBUTOR AGREEMENT",
            "paragraphs": [
                {
                    "context": CONTEXT,
                    "qas": [
                        {
                            "id": "ACMECO_01_01_2020-EX-10-DISTRIBUTOR AGREEMENT__Document Name",
                            "question": "Highlight the parts ... Details: The name of the contract",
                            "answers": [
                                {
                                    "text": "DISTRIBUTOR AGREEMENT",
                                    "answer_start": CONTEXT.index("DISTRIBUTOR AGREEMENT"),
                                }
                            ],
                            "is_impossible": False,
                        },
                        {
                            "id": "ACMECO_01_01_2020-EX-10-DISTRIBUTOR AGREEMENT__Governing Law",
                            "question": "Highlight ... Details: Which state's law governs",
                            "answers": [
                                {
                                    "text": "governed by the laws of Delaware",
                                    "answer_start": CONTEXT.index("governed by the laws"),
                                }
                            ],
                            "is_impossible": False,
                        },
                        {
                            "id": "ACMECO_01_01_2020-EX-10-DISTRIBUTOR AGREEMENT__Audit Rights",
                            "question": "Highlight ... Details: audit rights",
                            "answers": [],
                            "is_impossible": True,
                        },
                    ],
                }
            ],
        }
    ],
}


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    path = tmp_path_factory.mktemp("cuad") / "CUADv1.json"
    path.write_text(json.dumps(FIXTURE))
    return parse_cuad(path)


class TestParse:
    def test_only_answered_categories_become_clauses(self, parsed) -> None:
        """An unanswered category means the clause is *absent* from that contract. Storing it
        as a row with empty text would make "no audit rights clause" indistinguishable from
        "an audit rights clause we have no text for"."""
        assert len(parsed) == 2
        assert {c.clause_type for c in parsed} == {"Document Name", "Governing Law"}

    def test_offsets_are_read_from_the_corpus_not_reconstructed(self, parsed) -> None:
        context = CONTEXT
        for clause in parsed:
            assert context[clause.char_start : clause.char_end] == clause.text

    def test_clause_type_is_the_gold_label(self, parsed) -> None:
        governing = next(c for c in parsed if c.clause_type == "Governing Law")
        assert governing.text == "governed by the laws of Delaware"

    def test_industry_is_never_asserted_as_gold(self, parsed) -> None:
        assert all(c.is_inferred_industry for c in parsed)
        assert all(c.folio_industry_code is None for c in parsed)

    def test_ids_are_deterministic_so_reruns_upsert(self, parsed) -> None:
        first = parsed[0]
        again = clause_id(
            first.source_contract_title, first.clause_type, first.char_start, first.char_end
        )
        assert again == parsed[0].id
        assert len({c.id for c in parsed}) == len(parsed)


@needs_corpus
class TestRealCorpus:
    @pytest.fixture(scope="class")
    def clauses(self):
        return parse_cuad(CUAD_FILE)

    def test_510_contracts_and_41_categories(self, clauses) -> None:
        assert len({c.source_contract_title for c in clauses}) == 510
        assert len({c.clause_type for c in clauses}) == 41

    def test_provenance_spot_check(self, clauses) -> None:
        """The #8 test, applied to CUAD: 20 sampled rows must match their byte range."""
        contexts = {}
        for contract in json.loads(CUAD_FILE.read_text(encoding="utf-8"))["data"]:
            contexts[contract["title"]] = contract["paragraphs"][0]["context"]
        random.seed(10)
        for clause in random.sample(clauses, 20):
            source = contexts[clause.source_contract_title]
            assert source[clause.char_start : clause.char_end] == clause.text


@needs_corpus
class TestLoad:
    @pytest.fixture(scope="class")
    def loaded(self):
        clauses = parse_cuad(CUAD_FILE)
        with psycopg.connect(DSN) as conn:
            upsert_clauses(conn, clauses)
        return clauses

    def test_rows_land(self, loaded) -> None:
        with psycopg.connect(DSN) as conn:
            count = conn.execute("SELECT count(*) FROM clauses WHERE corpus = 'cuad'").fetchone()[0]
        assert count == len(loaded)

    def test_idempotent(self, loaded) -> None:
        with psycopg.connect(DSN) as conn:
            before = conn.execute("SELECT count(*) FROM clauses").fetchone()[0]
            upsert_clauses(conn, loaded)
            after = conn.execute("SELECT count(*) FROM clauses").fetchone()[0]
        assert after == before

    def test_no_cuad_row_claims_a_gold_industry(self, loaded) -> None:
        with psycopg.connect(DSN) as conn:
            gold = conn.execute(
                "SELECT count(*) FROM clauses WHERE corpus = 'cuad' AND NOT is_inferred_industry"
            ).fetchone()[0]
        assert gold == 0

    def test_cuad_does_not_contaminate_the_deal_universe(self, loaded) -> None:
        """`matters` is the comparable-deals universe — the 152 merger agreements. CUAD's 510
        commercial contracts are a clause corpus, not deals, and must not appear in a facet
        count that a partner reads as "comparable deals"."""
        with psycopg.connect(DSN) as conn:
            matters = conn.execute("SELECT count(*) FROM matters").fetchone()[0]
        assert matters == 152

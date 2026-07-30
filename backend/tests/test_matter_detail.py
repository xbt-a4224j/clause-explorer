"""`GET /matters/{id}` — the card's drill-through (#20).

The claim this endpoint has to survive is CLAUDE.md's provenance rule: a row whose text cannot
be traced to a byte range in the downloaded source is a bug. So the assertions here are mostly
about *refusing to invent text* — a span that does not resolve returns null with a reason, never
a plausible-looking excerpt and never a silent empty string.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM deal_points").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@needs_corpus
class TestTheCardsFields:
    def test_it_returns_the_parties_and_the_industry_with_its_inferred_flag(
        self, client: TestClient
    ) -> None:
        body = client.get("/matters/contract_1").json()
        assert body["matter_id"] == "contract_1"
        assert body["target_name"] == "ACCELERON PHARMA INC."
        assert body["industry"] == "Health Care Industry"
        # the crosswalk is not an expert label and the card must be able to say so
        assert body["is_inferred_industry"] is True

    def test_deal_value_is_null_rather_than_estimated(self, client: TestClient) -> None:
        """#9 is open. A card that shows an estimate as fact is the failure D25 avoided."""
        body = client.get("/matters/contract_1").json()
        assert body["deal_value_usd"] is None

    def test_it_carries_the_source_agreement_for_the_citation(self, client: TestClient) -> None:
        body = client.get("/matters/contract_1").json()
        assert body["source_file"]
        assert body["source_contract_title"]

    def test_an_unknown_matter_is_a_404_not_an_empty_card(self, client: TestClient) -> None:
        response = client.get("/matters/contract_does_not_exist")
        assert response.status_code == 404


@needs_corpus
class TestDealPoints:
    def test_the_matters_deal_points_come_back_with_their_positions(
        self, client: TestClient
    ) -> None:
        body = client.get("/matters/contract_1").json()
        assert body["deal_point_count"] > 0
        assert len(body["deal_points"]) == body["deal_point_count"]
        assert all(dp["deal_point_name"] and dp["position"] for dp in body["deal_points"])

    def test_every_deal_point_carries_its_denominator_context(self, client: TestClient) -> None:
        """The card reports "n of m located"; both numbers must come from the response."""
        body = client.get("/matters/contract_1").json()
        located = [dp for dp in body["deal_points"] if dp["source_span_start"] is not None]
        assert body["located_count"] == len(located)

    def test_deal_points_are_rows_not_columns(self, client: TestClient) -> None:
        """The LONG shape is the extensibility of the app (D8). A 93rd deal point must be a
        row here, never a new key on the response object."""
        body = client.get("/matters/contract_1").json()
        names = {dp["deal_point_name"] for dp in body["deal_points"]}
        assert len(names) > 1
        assert not any(n in body for n in names)


@needs_corpus
class TestDrillThroughIsTraceable:
    def test_a_located_deal_point_exposes_its_byte_range_and_file(self, client: TestClient) -> None:
        body = client.get("/matters/contract_1").json()
        located = next(dp for dp in body["deal_points"] if dp["source_span_start"] is not None)
        assert located["source_span_end"] > located["source_span_start"]
        assert body["source_file"].endswith(".txt")

    def test_clause_text_is_the_actual_slice_of_the_source_file(self, client: TestClient) -> None:
        """Not paraphrased, not re-extracted: the exact characters at those offsets."""
        from explorer.ingest.maud_corpus import CONTRACTS_DIR, corpus_available

        if not corpus_available():
            pytest.skip("MAUD corpus not downloaded")

        body = client.get("/matters/contract_1").json()
        located = next(
            dp
            for dp in body["deal_points"]
            if dp["source_span_start"] is not None and dp["clause_text"]
        )
        raw = (CONTRACTS_DIR / "contract_1.txt").read_text(encoding="utf-8", errors="replace")
        expected = raw[located["source_span_start"] : located["source_span_end"]]
        assert located["clause_text"] == expected

    def test_an_unlocated_deal_point_returns_null_text_with_a_reason(
        self, client: TestClient
    ) -> None:
        """495 of 12,937 rows have no span. Inventing text for them would be undetectable."""
        body = client.get("/matters/contract_1").json()
        unlocated = [dp for dp in body["deal_points"] if dp["source_span_start"] is None]
        for dp in unlocated:
            assert dp["clause_text"] is None
            assert dp["text_unavailable"]


@needs_corpus
class TestCopyableSummary:
    def test_the_summary_is_plain_text_and_cites_the_source_agreement(
        self, client: TestClient
    ) -> None:
        body = client.get("/matters/contract_1").json()
        summary = body["summary"]
        assert "<" not in summary  # pasted into a deck, not rendered
        assert body["source_contract_title"] in summary

    def test_the_summary_marks_an_inferred_industry_as_inferred(self, client: TestClient) -> None:
        """The paragraph leaves the app and loses the badge, so the word has to be in the text."""
        body = client.get("/matters/contract_1").json()
        assert body["is_inferred_industry"] is True
        assert "inferred" in body["summary"].lower()

    def test_the_summary_carries_a_denominator(self, client: TestClient) -> None:
        body = client.get("/matters/contract_1").json()
        assert f"n={body['deal_point_count']}" in body["summary"]

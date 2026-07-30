"""POST /comparables (#18).

The assertion the endpoint exists for is **filter before rank**. Ranking the corpus and then
dropping out-of-filter results returns fewer rows than asked for and scores relative to a
corpus the user did not request — and both failures look like ordinary results.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")
HEALTH_CARE = "RCSG4k3ah1Pu5YgPexPgOmL"
INDUSTRY_LEVEL_2 = "RDIwFaFcH4KY0gwEY0QlMTp"  # "Industry", parent of the sector codes


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM matters").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def cached_query() -> str:
    """A description that is in the committed embedding cache.

    Free-text ranking needs the query embedded. With no key, only cached text can be ranked —
    that is the deliberate contract (#16), not a limitation to work around, so the no-key tests
    use a query warm_cache embedded and TestUncachedQuery asserts what happens otherwise.
    """
    from explorer.evals.retrieval_set import build_eval_set

    return next(q.query for q in build_eval_set(DSN) if q.template == "industry_year")


@needs_corpus
class TestFiltering:
    def test_industry_filter_constrains_the_candidate_set(self, client: TestClient) -> None:
        body = client.post("/comparables", json={"folio_industry_code": HEALTH_CARE}).json()
        assert body["candidate_count"] == 25
        assert {m["industry"] for m in body["matters"]} == {"Health Care Industry"}

    def test_an_out_of_filter_matter_never_appears(
        self, client: TestClient, cached_query: str
    ) -> None:
        """Filter before rank: whatever the description ranks toward, nothing outside the
        health-care filter can appear."""
        body = client.post(
            "/comparables",
            json={
                "folio_industry_code": HEALTH_CARE,
                "description": cached_query,
                "limit": 25,
            },
        ).json()
        assert body["matters"], "filtering must not empty the result"
        assert all(m["industry"] == "Health Care Industry" for m in body["matters"])

    def test_hierarchy_rolls_up(self, client: TestClient) -> None:
        """Filtering on the level-2 'Industry' concept matches every sector beneath it."""
        body = client.post("/comparables", json={"folio_industry_code": INDUSTRY_LEVEL_2}).json()
        assert body["candidate_count"] == 134  # every classified matter
        assert body["applied_filters"]["rolled_up_to_descendants"] > 0

    def test_date_range_filters(self, client: TestClient) -> None:
        body = client.post(
            "/comparables", json={"signed_from": "2021-01-01", "signed_to": "2021-12-31"}
        ).json()
        assert 0 < body["candidate_count"] < 152

    def test_unknown_folio_code_is_a_loud_error_not_an_empty_list(self, client: TestClient) -> None:
        """Zero results and a bad code look identical to a reader — the nastiest failure mode
        in the design (CLAUDE.md)."""
        response = client.post("/comparables", json={"folio_industry_code": "R_NOT_A_CODE"})
        assert response.status_code == 400
        assert "does not exist" in response.json()["error"]["message"]


@needs_corpus
class TestRanking:
    def test_scores_are_returned_per_matter(self, client: TestClient, cached_query: str) -> None:
        body = client.post(
            "/comparables",
            json={"description": cached_query, "limit": 10},
        ).json()
        top = body["matters"][0]
        assert top["score"] is not None
        assert top["vector_score"] is not None and top["bm25_score"] is not None

    def test_ranking_actually_reorders(self, client: TestClient, cached_query: str) -> None:
        ranked = client.post(
            "/comparables", json={"description": cached_query, "limit": 10}
        ).json()["matters"]
        unranked = client.post("/comparables", json={"limit": 10}).json()["matters"]
        assert [m["matter_id"] for m in ranked] != [m["matter_id"] for m in unranked]

    def test_alpha_is_accepted_per_request(self, client: TestClient, cached_query: str) -> None:
        body = client.post(
            "/comparables", json={"description": cached_query, "alpha": 0.0, "limit": 3}
        ).json()
        assert body["applied_filters"]["ranked_by"] == "hybrid alpha=0.0"


@needs_corpus
class TestAppliedFiltersAreReported:
    def test_response_says_what_was_actually_applied(self, client: TestClient) -> None:
        """Feeds the resolved-query display (#23, #26) so a domain expert can catch a
        misinterpretation before quoting the number."""
        body = client.post(
            "/comparables",
            json={"folio_industry_code": HEALTH_CARE, "signed_from": "2021-01-01"},
        ).json()
        applied = body["applied_filters"]
        assert applied["folio_industry_label"] == "Health Care Industry"
        assert applied["signed_from"] == "2021-01-01"
        assert applied["ranked_by"] == "matter id (no description given)"

    def test_inferred_industry_is_flagged_on_every_matter(self, client: TestClient) -> None:
        body = client.post("/comparables", json={"folio_industry_code": HEALTH_CARE}).json()
        assert all(m["is_inferred_industry"] for m in body["matters"])


@needs_corpus
@pytest.mark.skipif(bool(os.getenv("OPENAI_API_KEY")), reason="asserts the no-key path")
class TestUncachedQueryWithoutAKey:
    def test_returns_503_naming_the_cached_count_not_a_bare_500(self, client: TestClient) -> None:
        """The designed contract: never a silent API call, never an unexplained failure. The
        message has to tell the operator how many vectors exist and what command adds more."""
        response = client.post(
            "/comparables",
            json={"description": "a phrase nobody has ever embedded before, truly novel"},
        )
        assert response.status_code == 503
        message = response.json()["error"]["message"]
        assert "embedding cache" in message
        assert "warm_cache" in message

"""`GET /tables/*` — browsable views so nobody opens psql (#31).

Server-side sort, filter, and pagination is the whole point: the frontend must never be able to
load a whole table, so what earns a test is that the limit is enforced, that only whitelisted
tables and columns can ever reach a query, and that the schema/null-count metadata is real.

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
            return conn.execute("SELECT count(*) FROM matters").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestTableWhitelist:
    def test_an_unknown_table_name_is_rejected_not_queried(self, client: TestClient) -> None:
        response = client.get("/tables/pg_shadow/rows")
        assert response.status_code == 404

    def test_sql_injection_in_the_table_name_is_rejected(self, client: TestClient) -> None:
        response = client.get("/tables/matters%3B%20DROP%20TABLE%20matters/rows")
        assert response.status_code in (404, 422)

    def test_sorting_by_an_unknown_column_is_rejected(self, client: TestClient) -> None:
        response = client.get("/tables/matters/rows", params={"sort": "id; DROP TABLE matters"})
        assert response.status_code == 422


@needs_corpus
class TestBrowsing:
    def test_matters_returns_the_real_row_count(self, client: TestClient) -> None:
        body = client.get("/tables/matters/rows", params={"limit": 5}).json()
        assert body["total_count"] == 152
        assert len(body["rows"]) == 5

    def test_pagination_never_returns_more_than_the_limit(self, client: TestClient) -> None:
        body = client.get("/tables/deal_points/rows", params={"limit": 10, "offset": 20}).json()
        assert len(body["rows"]) == 10

    def test_a_limit_above_the_ceiling_is_rejected_not_silently_capped(
        self, client: TestClient
    ) -> None:
        """The AC: the frontend must never be able to load a whole table. A silent cap would
        let a client believe it asked for everything when it did not."""
        response = client.get("/tables/deal_points/rows", params={"limit": 100000})
        assert response.status_code == 422

    def test_sort_is_applied_server_side(self, client: TestClient) -> None:
        asc = client.get(
            "/tables/matters/rows", params={"sort": "id", "dir": "asc", "limit": 3}
        ).json()
        desc = client.get(
            "/tables/matters/rows", params={"sort": "id", "dir": "desc", "limit": 3}
        ).json()
        assert [r["id"] for r in asc["rows"]] != [r["id"] for r in desc["rows"]]

    def test_a_column_filter_narrows_the_total_count(self, client: TestClient) -> None:
        all_rows = client.get("/tables/deal_points/rows", params={"limit": 1}).json()
        filtered = client.get(
            "/tables/deal_points/rows",
            params={
                "filter_column": "deal_point_name",
                "filter_value": "Ability to consummate",
                "limit": 1,
            },
        ).json()
        assert filtered["total_count"] < all_rows["total_count"]
        assert filtered["total_count"] > 0

    def test_row_expansion_returns_the_full_record(self, client: TestClient) -> None:
        listing = client.get("/tables/matters/rows", params={"limit": 1}).json()
        row_id = listing["rows"][0]["id"]
        full = client.get(f"/tables/matters/rows/{row_id}").json()
        assert full["id"] == row_id
        assert "source_file" in full


@needs_corpus
class TestSchema:
    def test_reports_column_type_and_null_count(self, client: TestClient) -> None:
        body = client.get("/tables/matters/schema").json()
        col = next(c for c in body["columns"] if c["name"] == "deal_value_usd")
        assert col["type"]
        assert col["null_count"] == 152  # #9 open: every matter's deal value is NULL

    def test_row_count_is_on_the_schema_response_too(self, client: TestClient) -> None:
        body = client.get("/tables/matters/schema").json()
        assert body["row_count"] == 152


@needs_corpus
class TestInferredFieldsAreFlagged:
    def test_the_schema_marks_which_columns_are_inferred(self, client: TestClient) -> None:
        """Consistent with the matter card (#20): is_inferred_industry etc. are flagged, same
        naming convention, read generically rather than hardcoded per table."""
        body = client.get("/tables/matters/schema").json()
        inferred_cols = {c["name"] for c in body["columns"] if c["is_inferred_flag"]}
        assert "is_inferred_industry" in inferred_cols
        assert "target_name" not in inferred_cols


@needs_corpus
class TestCSVExport:
    def test_exports_the_current_filtered_view_as_csv(self, client: TestClient) -> None:
        response = client.get(
            "/tables/deal_points/export.csv",
            params={"filter_column": "deal_point_name", "filter_value": "Ability to consummate"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        body = response.text
        assert body.count("\n") > 1  # header + at least one data row
        assert "Ability to consummate" in body

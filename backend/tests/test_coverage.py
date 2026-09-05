"""`POST /coverage` — the industry × period grid (#22).

The KM view, and a deliberate design inversion: default BI styling emphasises the big numbers,
but a gap is more actionable than a strength you already know about. The API's job is to make
thinness explicit — every cell says whether it is reportable and why — so the view cannot
accidentally render a thin cell as an ordinary one.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
import pytest
from explorer.api import coverage as module
from explorer.api.cube_client import CubeUnavailable
from explorer.api.main import app
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

LABEL = "comparable_deals.label"
CODE = "comparable_deals.code"
YEAR = "comparable_deals.signing_year"
BAND = "comparable_deals.deal_size_band"
N = "comparable_deals.n"

GRID = [
    {LABEL: "Health Care Industry", CODE: "hc", YEAR: "2021", N: 19},
    {LABEL: "Health Care Industry", CODE: "hc", YEAR: "2020", N: 6},
    {LABEL: "Manufacturing Industry", CODE: "mf", YEAR: "2021", N: 4},
    {LABEL: "Manufacturing Industry", CODE: "mf", YEAR: "2020", N: 18},
    {LABEL: "Information Industry", CODE: "in", YEAR: "2021", N: 1},
]


class StubCube:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = GRID if rows is None else rows
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
        self.payloads.append(payload)
        return self.rows


@pytest.fixture
def cube(monkeypatch: pytest.MonkeyPatch) -> StubCube:
    stub = StubCube()
    monkeypatch.setattr(module, "cube_query", stub)
    return stub


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _cell(body: dict[str, Any], row: str, column: str) -> dict[str, Any]:
    r = next(x for x in body["rows"] if x["label"] == row)
    return next(c for c in r["cells"] if c["column"] == column)


class TestThinnessIsExplicit:
    def test_a_cell_below_min_n_is_marked_not_reportable(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/coverage", json={}).json()
        thin = _cell(body, "Manufacturing Industry", "2021")  # n=4, min_n=5
        assert thin["n"] == 4
        assert thin["reportable"] is False
        assert "insufficient to characterize" in thin["note"].lower()

    def test_a_cell_at_min_n_is_reportable(self, client: TestClient, cube: StubCube) -> None:
        """The boundary is inclusive, and it is the same threshold #23 refuses on."""
        body = client.post("/coverage", json={}).json()
        at = _cell(body, "Health Care Industry", "2020")  # n=6 with min_n=5
        assert at["reportable"] is True
        assert at["note"] is None

    def test_the_threshold_in_force_is_reported(self, client: TestClient, cube: StubCube) -> None:
        body = client.post("/coverage", json={}).json()
        assert body["min_n"] == module.settings.min_n

    def test_an_empty_cell_exists_rather_than_being_absent(
        self, client: TestClient, cube: StubCube
    ) -> None:
        """A gap is the finding. Information Industry has no 2020 row in the data at all; it
        must still render as a zero cell, or the grid silently hides where we have nothing."""
        body = client.post("/coverage", json={}).json()
        gap = _cell(body, "Information Industry", "2020")
        assert gap["n"] == 0
        assert gap["reportable"] is False


class TestTotals:
    def test_every_row_carries_its_total(self, client: TestClient, cube: StubCube) -> None:
        body = client.post("/coverage", json={}).json()
        row = next(r for r in body["rows"] if r["label"] == "Health Care Industry")
        assert row["total_n"] == 25

    def test_every_column_carries_its_total(self, client: TestClient, cube: StubCube) -> None:
        body = client.post("/coverage", json={}).json()
        assert body["column_totals"]["2021"] == 19 + 4 + 1
        assert body["column_totals"]["2020"] == 6 + 18

    def test_the_grid_total_is_the_sum_of_the_cells(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/coverage", json={}).json()
        assert body["total_n"] == sum(r[N] for r in GRID)


class TestDrillTarget:
    def test_each_cell_carries_what_explore_needs_to_pre_filter(
        self, client: TestClient, cube: StubCube
    ) -> None:
        """Clicking a cell must filter by industry code, not by the display label (#25)."""
        body = client.post("/coverage", json={}).json()
        cell = _cell(body, "Health Care Industry", "2021")
        assert cell["folio_industry_code"] == "hc"
        assert cell["column"] == "2021"


class TestTheColumnAxis:
    def test_it_groups_by_year_by_default(self, client: TestClient, cube: StubCube) -> None:
        client.post("/coverage", json={})
        assert YEAR in cube.payloads[0]["dimensions"]

    def test_deal_size_can_be_requested_and_says_it_carries_no_data(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#22 specifies deal size as the column axis. `deal_value_usd` is NULL on all 152
        matters (#9), so that grid is one column wide. It is offered and labelled, never
        silently substituted."""
        stub = StubCube([{LABEL: "Health Care Industry", CODE: "hc", BAND: "unknown", N: 25}])
        monkeypatch.setattr(module, "cube_query", stub)
        body = client.post("/coverage", json={"column": "band"}).json()
        assert BAND in stub.payloads[0]["dimensions"]
        assert "no deal values" in body["column_note"].lower()

    def test_the_default_axis_says_why_it_is_not_deal_size(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/coverage", json={}).json()
        assert body["column_axis"] == "year"
        assert "deal size" in body["column_note"].lower()

    def test_an_unknown_axis_is_rejected(self, client: TestClient, cube: StubCube) -> None:
        assert client.post("/coverage", json={"column": "nonsense"}).status_code == 422


class TestCubeFailureIsNotAnEmptyGrid:
    def test_an_unavailable_cube_is_a_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
            raise CubeUnavailable("Cube did not answer")

        monkeypatch.setattr(module, "cube_query", boom)
        assert client.post("/coverage", json={}).status_code == 503


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM matters").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


@pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
class TestAgainstRealCube:
    def test_the_grid_totals_reconcile_to_the_corpus(self, client: TestClient) -> None:
        body = client.post("/coverage", json={}).json()
        assert body["total_n"] == sum(c["n"] for r in body["rows"] for c in r["cells"]), (
            "the grid must account for every matter it counts"
        )

    def test_thin_cells_exist_and_are_marked(self, client: TestClient) -> None:
        """If this stops being true the corpus grew; the checkpoint answer changes with it."""
        body = client.post("/coverage", json={}).json()
        thin = [c for r in body["rows"] for c in r["cells"] if not c["reportable"]]
        assert thin, "the coverage grid's whole thesis is that thin cells exist"
        assert all(c["note"] for c in thin)

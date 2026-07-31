"""POST /facets (#19).

The facet rail is the partner's only view of what the corpus can answer, so its failure modes
are all quiet ones: a group that filters itself collapses to one value and traps the user; a
dropped zero-count value silently rewrites "we have nothing there" into "that option does not
exist"; and a dead Cube that returns `[]` is indistinguishable from an honestly empty slice.

Cube is stubbed here on purpose. These are assertions about *our* query construction and
response shaping, and they must run in the no-key gate with no container up. The live-stack
check is in the worklog, run against real Cube.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

from typing import Any

import pytest
from explorer.api import facets as facets_module
from explorer.api.cube_client import CubeUnavailable
from explorer.api.facets import (
    BAND_DIMENSION,
    CODE_DIMENSION,
    COUNT_MEASURE,
    DEAL_POINT_COUNT,
    INDUSTRY_DIMENSION,
    YEAR_DIMENSION,
)
from explorer.api.main import app
from fastapi.testclient import TestClient

INDUSTRY_ROWS = [
    {
        INDUSTRY_DIMENSION: "Health Care Industry",
        CODE_DIMENSION: "RCSG4k3ah1Pu5YgPexPgOmL",
        COUNT_MEASURE: 25,
    },
    {
        INDUSTRY_DIMENSION: "Manufacturing Industry",
        CODE_DIMENSION: "RBxLbTLwMitsqvA0VkYFxJf",
        COUNT_MEASURE: 22,
    },
    {
        INDUSTRY_DIMENSION: "Educational Services Industry",
        CODE_DIMENSION: "REduPlaceholder00000001",
        COUNT_MEASURE: 0,
    },
    # 18 matters have no FOLIO industry: a real bucket with no concept behind it
    {INDUSTRY_DIMENSION: None, CODE_DIMENSION: None, COUNT_MEASURE: 18},
]
YEAR_ROWS = [
    {YEAR_DIMENSION: "2021", COUNT_MEASURE: 116},
    {YEAR_DIMENSION: "2020", COUNT_MEASURE: 33},
]
BAND_ROWS = [{BAND_DIMENSION: "unknown", COUNT_MEASURE: 152}]


class StubCube:
    """Records every payload, answers by which dimension was asked for."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
        self.payloads.append(payload)
        dimensions = payload.get("dimensions") or []
        measures = payload.get("measures") or []
        if INDUSTRY_DIMENSION in dimensions:
            return list(INDUSTRY_ROWS)
        if YEAR_DIMENSION in dimensions:
            return list(YEAR_ROWS)
        if BAND_DIMENSION in dimensions:
            return list(BAND_ROWS)
        if DEAL_POINT_COUNT in measures:
            return [{DEAL_POINT_COUNT: 12937}]
        return [{COUNT_MEASURE: 152}]

    def payload_for(self, dimension: str) -> dict[str, Any]:
        return next(p for p in self.payloads if dimension in (p.get("dimensions") or []))


@pytest.fixture
def cube(monkeypatch: pytest.MonkeyPatch) -> StubCube:
    stub = StubCube()
    monkeypatch.setattr(facets_module, "cube_query", stub)
    return stub


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _group(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(g for g in body["groups"] if g["key"] == key)


class TestSelfFiltering:
    """A facet group must not narrow itself, or selecting a value hides the alternatives."""

    def test_the_industry_group_is_not_filtered_by_the_selected_industry(
        self, client: TestClient, cube: StubCube
    ) -> None:
        client.post("/facets", json={"folio_industry_label": "Health Care Industry"})
        members = [f["member"] for f in cube.payload_for(INDUSTRY_DIMENSION)["filters"]]
        assert INDUSTRY_DIMENSION not in members

    def test_other_groups_are_filtered_by_the_selected_industry(
        self, client: TestClient, cube: StubCube
    ) -> None:
        client.post("/facets", json={"folio_industry_label": "Health Care Industry"})
        year_filters = cube.payload_for(YEAR_DIMENSION)["filters"]
        assert [f["member"] for f in year_filters] == [INDUSTRY_DIMENSION]
        assert year_filters[0]["values"] == ["Health Care Industry"]

    def test_the_selected_value_is_marked_selected(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={"folio_industry_label": "Health Care Industry"}).json()
        selected = [v["value"] for v in _group(body, "industry")["values"] if v["selected"]]
        assert selected == ["Health Care Industry"]


class TestIndustryCarriesItsCode:
    """The rail hands /comparables a FOLIO code, never a display label.

    Filtering by the string a human reads is the failure mode #25 exists for: "Health Care"
    against "Health Care Industry" returns zero rows that look exactly like "no comparable
    deals". The code is the join key and cannot drift, so it travels with the label.
    """

    def test_each_industry_value_carries_its_folio_code(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={}).json()
        codes = {v["value"]: v["code"] for v in _group(body, "industry")["values"]}
        assert codes["Health Care Industry"] == "RCSG4k3ah1Pu5YgPexPgOmL"

    def test_the_unclassified_bucket_has_no_code(self, client: TestClient, cube: StubCube) -> None:
        """Matters with no industry are a real bucket, but there is no concept to filter by —
        a fabricated code here would silently return nothing."""
        body = client.post("/facets", json={}).json()
        codes = {v["value"]: v["code"] for v in _group(body, "industry")["values"]}
        assert codes["unclassified"] is None

    def test_a_group_without_a_code_dimension_leaves_code_unset(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={}).json()
        assert all(v["code"] is None for v in _group(body, "year")["values"])


class TestCorpusCountsAreVisibleBeforeAnyInteraction:
    """Demo script 1 beat 1: matters, deal points and industries on landing.

    Without them the partner cannot tell whether an empty-looking rail means a small corpus or
    a broken ingest.
    """

    def test_the_response_carries_the_corpus_totals(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={}).json()
        assert body["corpus"]["matters"] == 152
        assert body["corpus"]["deal_points"] == 12937
        # 2, not 3: "unclassified" is a bucket rather than an industry, and Educational
        # Services has n=0 — an industry the corpus holds nothing in is not one it covers
        assert body["corpus"]["industries"] == 2


class TestZeroCounts:
    def test_a_zero_count_value_is_returned_not_dropped(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={}).json()
        values = {v["value"]: v["n"] for v in _group(body, "industry")["values"]}
        assert values["Educational Services Industry"] == 0

    def test_a_null_dimension_value_is_labelled_not_discarded(
        self, client: TestClient, cube: StubCube
    ) -> None:
        """18 matters have no FOLIO industry. Dropping them makes the group totals lie."""
        body = client.post("/facets", json={}).json()
        values = {v["value"]: v["n"] for v in _group(body, "industry")["values"]}
        assert values["unclassified"] == 18


class TestDenominators:
    def test_every_group_carries_its_own_total(self, client: TestClient, cube: StubCube) -> None:
        body = client.post("/facets", json={}).json()
        assert _group(body, "industry")["total_n"] == 25 + 22 + 0 + 18
        assert _group(body, "year")["total_n"] == 116 + 33

    def test_the_response_carries_both_selected_and_unfiltered_totals(
        self, client: TestClient, cube: StubCube
    ) -> None:
        """The rail renders "n of 152"; without the unfiltered total there is no denominator."""
        body = client.post("/facets", json={}).json()
        assert body["total_n"] == 152
        assert body["unfiltered_n"] == 152


class TestDealSizeBand:
    """`deal_value_usd` is NULL on all 152 matters (#9 open), so this group can only report
    `unknown`. It ships anyway, disabled with a stated reason: a rail that omits deal size
    implies the corpus has no such axis, when in fact the axis exists and the data is missing.
    Those are different claims and only one of them is true.
    """

    def test_the_band_group_is_present_even_though_only_unknown_exists(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={}).json()
        assert [v["value"] for v in _group(body, "band")["values"]] == ["unknown"]

    def test_a_group_with_no_real_values_carries_a_reason(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={}).json()
        assert "no deal values have been enriched yet" in _group(body, "band")["unavailable"]

    def test_a_group_with_real_values_carries_no_reason(
        self, client: TestClient, cube: StubCube
    ) -> None:
        """The reason must not become permanent furniture — it disappears when #9 lands."""
        body = client.post("/facets", json={}).json()
        assert _group(body, "industry")["unavailable"] is None
        assert _group(body, "year")["unavailable"] is None


class TestCubeFailureIsNotAnEmptyResult:
    def test_an_unavailable_cube_is_a_503_not_zero_counts(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
            raise CubeUnavailable("Cube did not answer")

        monkeypatch.setattr(facets_module, "cube_query", boom)
        response = client.post("/facets", json={})
        assert response.status_code == 503
        assert "Cube did not answer" in response.text


class TestYearIsComparedAsAString:
    """`signing_year` is `to_char(signing_date, 'YYYY')` — a string dimension, not a number.

    Cube's `equals` does not coerce across types: sending the integer 2021 against a string
    dimension matches nothing and returns an empty rail that reads as "no 2021 deals". The
    request still accepts an int, because that is what a caller naturally sends.
    """

    def test_an_int_year_reaches_cube_as_a_string(self, client: TestClient, cube: StubCube) -> None:
        client.post("/facets", json={"signing_year": 2021})
        year_filter = next(
            f
            for f in cube.payload_for(INDUSTRY_DIMENSION)["filters"]
            if f["member"] == YEAR_DIMENSION
        )
        assert year_filter["values"] == ["2021"]

    def test_the_selected_year_is_matched_against_the_string_rows(
        self, client: TestClient, cube: StubCube
    ) -> None:
        body = client.post("/facets", json={"signing_year": 2021}).json()
        selected = [v["value"] for v in _group(body, "year")["values"] if v["selected"]]
        assert selected == ["2021"]

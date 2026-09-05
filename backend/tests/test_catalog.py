"""`GET /agent/catalog` (#36).

The catalog is the vocabulary the model may select from — and it is the same list an offline
eval grades against. That equivalence is the whole argument for the semantic layer, so what
earns a test is that the endpoint reads Cube's live metadata rather than a checked-in copy
that can drift from `cube/model/*.yml`, and that it survives Cube being down without
pretending the vocabulary is empty.
"""

from __future__ import annotations

from typing import Any

import pytest
from explorer.api.cube_client import CubeUnavailable
from explorer.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


META = {
    "cubes": [
        {
            "name": "deal_points",
            "title": "Deal Points",
            "measures": [
                {
                    "name": "deal_points.n",
                    "title": "N",
                    "type": "count",
                    "description": "matters answering this deal point",
                },
                {
                    "name": "deal_points.median_numeric_value",
                    "title": "Median",
                    "type": "number",
                    "description": "percentile_cont(0.5), never avg",
                },
            ],
            "dimensions": [
                {
                    "name": "deal_points.deal_point_name",
                    "title": "Deal Point",
                    "type": "string",
                    "description": "one of the 92 ABA public target deal points",
                }
            ],
        }
    ]
}


@pytest.fixture
def cube_meta(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr("explorer.api.catalog.meta", lambda: META)
    return META


class TestCatalog:
    def test_lists_measures_the_model_may_select(self, cube_meta: dict[str, Any]) -> None:
        body = client.get("/agent/catalog").json()
        names = {m["name"] for m in body["measures"]}
        assert "deal_points.n" in names
        assert "deal_points.median_numeric_value" in names

    def test_lists_dimensions_separately_from_measures(self, cube_meta: dict[str, Any]) -> None:
        body = client.get("/agent/catalog").json()
        assert {d["name"] for d in body["dimensions"]} == {"deal_points.deal_point_name"}
        assert all("deal_point_name" not in m["name"] for m in body["measures"])

    def test_carries_descriptions(self, cube_meta: dict[str, Any]) -> None:
        """The description is what makes a selection reviewable by someone who did not write
        the model — without it the catalog is a list of opaque identifiers."""
        body = client.get("/agent/catalog").json()
        median = next(m for m in body["measures"] if m["name"].endswith("median_numeric_value"))
        assert "percentile_cont" in median["description"]

    def test_reports_the_label_space_size(self, cube_meta: dict[str, Any]) -> None:
        """An offline eval grades a selection against this vocabulary; its size is the claim
        that correctness here is discrete rather than freeform."""
        body = client.get("/agent/catalog").json()
        assert body["label_space"] == len(body["measures"]) + len(body["dimensions"])

    def test_needs_no_api_key(self, cube_meta: dict[str, Any], monkeypatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert client.get("/agent/catalog").status_code == 200

    def test_cube_down_is_503_not_an_empty_vocabulary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty catalog reads as "the model may select nothing", which is a different and
        much worse claim than "the semantic layer is unreachable"."""

        def boom() -> dict[str, Any]:
            raise CubeUnavailable("down")

        monkeypatch.setattr("explorer.api.catalog.meta", boom)
        response = client.get("/agent/catalog")
        assert response.status_code == 503
        assert "data" not in response.json()


# --- the catalog is the SELECTABLE vocabulary, not every cube -------------------------------
#
# Found by walking the Ask tab. The builder listed `matters.industry_code` and
# `industries.label` as things to group by, and `POST /agent/run-selection` answered
# "'matters.industry_code' is not a known dimension" — an error the UI produced by offering the
# option. `select.py` has restricted the agent to `comparable_deals` and `deal_points` since
# #24 and this endpoint never applied the same restriction.
#
# The label-space figure was the worse half. The tab renders "Label space: 48 — the model
# chooses from these names and no others, and an offline eval grades against exactly this
# list", and the model actually chose from 30. That is the tab's headline gradeability claim,
# published wrong by 18, on the one screen whose purpose is to make the claim checkable.

WIDE_META: dict[str, Any] = {
    "cubes": [
        {
            "name": "deal_points",
            "measures": [
                {"name": "deal_points.n", "title": "N", "type": "count"},
                {
                    "name": "deal_points.mean_numeric_value_do_not_use_for_market",
                    "title": "Mean",
                    "type": "number",
                },
            ],
            "dimensions": [{"name": "deal_points.position", "title": "Position"}],
        },
        {
            "name": "comparable_deals",
            "measures": [{"name": "comparable_deals.n", "title": "N", "type": "count"}],
            "dimensions": [{"name": "comparable_deals.label", "title": "Label"}],
        },
        {
            "name": "matters",
            "measures": [{"name": "matters.n", "title": "N", "type": "count"}],
            "dimensions": [{"name": "matters.industry_code", "title": "Industry Code"}],
        },
        {
            "name": "industries",
            "measures": [],
            "dimensions": [{"name": "industries.label", "title": "Label"}],
        },
    ]
}


@pytest.fixture
def wide_meta(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr("explorer.api.catalog.meta", lambda: WIDE_META)
    return WIDE_META


class TestTheCatalogIsWhatCanActuallyBeSelected:
    def test_a_cube_the_agent_cannot_select_from_is_not_listed(
        self, wide_meta: dict[str, Any]
    ) -> None:
        body = client.get("/agent/catalog").json()
        names = {d["name"] for d in body["dimensions"]} | {m["name"] for m in body["measures"]}
        assert "matters.industry_code" not in names
        assert "industries.label" not in names
        assert "matters.n" not in names

    def test_the_measure_excluded_by_name_is_excluded_here_too(
        self, wide_meta: dict[str, Any]
    ) -> None:
        """`..._do_not_use_for_market` exists so calibration can show how far the mean diverges
        from the median. Listing it in a picker makes it selectable regardless of what the name
        says — which is the exact argument `select.py` makes for excluding it structurally."""
        body = client.get("/agent/catalog").json()
        assert all("do_not_use_for_market" not in m["name"] for m in body["measures"])

    def test_the_label_space_is_the_number_a_selection_is_graded_against(
        self, wide_meta: dict[str, Any]
    ) -> None:
        """The claim on the tab is "the model chooses from these names and no others". The
        number has to be that set's size or the claim is false where it is loudest."""
        from explorer.agent.select import fetch_vocabulary

        vocabulary = fetch_vocabulary(WIDE_META)
        body = client.get("/agent/catalog").json()
        assert body["label_space"] == len(vocabulary.measures) + len(vocabulary.dimensions)
        assert {m["name"] for m in body["measures"]} == set(vocabulary.measures)
        assert {d["name"] for d in body["dimensions"]} == set(vocabulary.dimensions)

    def test_everything_the_catalog_offers_survives_selection_validation(
        self, wide_meta: dict[str, Any]
    ) -> None:
        """The property that was broken: a name a picker offers must not be one the run path
        refuses. This is the assertion, rather than the cube list, because the cube list is how
        it is implemented today and this is what it owes."""
        from explorer.agent.select import fetch_vocabulary, validate_selection

        vocabulary = fetch_vocabulary(WIDE_META)
        body = client.get("/agent/catalog").json()
        validate_selection(
            {
                "measures": [m["name"] for m in body["measures"]],
                "dimensions": [d["name"] for d in body["dimensions"]],
                "filters": [],
                "timeDimensions": [],
            },
            vocabulary,
        )

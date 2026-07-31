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

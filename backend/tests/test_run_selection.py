"""`POST /agent/run-selection` (#37) — run a selection the user built by clicking.

The Semantic Layer builder has no free-text box, so the client cannot construct an invalid
name. That is a UI property, not a guarantee, and this endpoint is the guarantee: every name is
checked against the live catalog *before* anything reaches Cube. Without that check the builder
is an argument rather than a demonstration, and an unvalidated passthrough would also hand a
caller arbitrary query construction.

What earns a test here: validation happens before Cube is touched at all, the min_n gate applies
on this path exactly as it does on the dashboard path, and a refusal is shaped differently from
an empty result.
"""

from __future__ import annotations

from typing import Any

import pytest
from explorer.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

VOCAB = {
    "cubes": [
        {
            "name": "deal_points",
            "measures": [
                {"name": "deal_points.n", "title": "N", "type": "count", "description": "d"},
                {
                    "name": "deal_points.median_numeric_value",
                    "title": "Median",
                    "type": "number",
                    "description": "percentile_cont",
                },
            ],
            "dimensions": [
                {
                    "name": "deal_points.deal_point_name",
                    "title": "Deal Point",
                    "type": "string",
                    "description": "d",
                }
            ],
        }
    ]
}


@pytest.fixture
def cube(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Records what reached Cube, so a test can assert it was never reached."""
    calls: dict[str, list[Any]] = {"queries": []}

    def fake_query(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
        calls["queries"].append(payload)
        return [{"deal_points.n": 25, "deal_points.median_numeric_value": 4.2}]

    monkeypatch.setattr("explorer.api.run_selection.cube_query", fake_query)
    monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
    return calls


def _vocab() -> Any:
    from explorer.agent.select import fetch_vocabulary

    return fetch_vocabulary(VOCAB)


class TestValidationHappensBeforeCube:
    def test_an_unknown_measure_is_rejected(self, cube: dict[str, list[Any]]) -> None:
        response = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.invented"], "dimensions": []}
        )
        assert response.status_code == 422

    def test_an_unknown_measure_never_reaches_cube(self, cube: dict[str, list[Any]]) -> None:
        """The ordering is the whole point: rejecting after the query has run would still return
        a 422 while having executed whatever was asked for."""
        client.post(
            "/agent/run-selection", json={"measures": ["deal_points.invented"], "dimensions": []}
        )
        assert cube["queries"] == []

    def test_an_unknown_dimension_is_rejected(self, cube: dict[str, list[Any]]) -> None:
        response = client.post(
            "/agent/run-selection",
            json={"measures": ["deal_points.n"], "dimensions": ["matters.invented"]},
        )
        assert response.status_code == 422

    def test_a_filter_on_an_unknown_field_is_rejected(self, cube: dict[str, list[Any]]) -> None:
        response = client.post(
            "/agent/run-selection",
            json={
                "measures": ["deal_points.n"],
                "dimensions": [],
                "filters": [{"member": "matters.secret", "operator": "equals", "values": ["x"]}],
            },
        )
        assert response.status_code == 422

    def test_the_error_names_the_offending_field(self, cube: dict[str, list[Any]]) -> None:
        response = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.invented"], "dimensions": []}
        )
        assert "deal_points.invented" in response.text


class TestAValidSelectionRuns:
    def test_it_returns_rows_and_the_query_that_produced_them(
        self, cube: dict[str, list[Any]]
    ) -> None:
        """The builder shows the query JSON next to the result; if the endpoint echoed a
        different query than it ran, the panel would be a lie."""
        body = client.post(
            "/agent/run-selection",
            json={
                "measures": ["deal_points.n"],
                "dimensions": ["deal_points.deal_point_name"],
            },
        ).json()
        assert body["rows"]
        assert body["query"] == cube["queries"][0]

    def test_it_reports_n_alongside_the_result(self, cube: dict[str, list[Any]]) -> None:
        body = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.n"], "dimensions": []}
        ).json()
        assert body["n"] == 25

    def test_it_needs_no_api_key(self, cube: dict[str, list[Any]], monkeypatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        response = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.n"], "dimensions": []}
        )
        assert response.status_code == 200


class TestMinNAppliesHereToo:
    def test_a_thin_slice_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query",
            lambda payload, timeout=20.0: [{"deal_points.n": 3}],
        )
        body = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.n"], "dimensions": []}
        ).json()
        assert body["refused"] is True
        assert body["n"] == 3
        assert body["threshold"] == 5

    def test_a_refusal_is_not_shaped_like_an_empty_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A caller must not be able to mistake "we will not answer" for "there is nothing
        here" — they are different statements and only one of them is about the data."""
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query",
            lambda payload, timeout=20.0: [{"deal_points.n": 2}],
        )
        body = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.n"], "dimensions": []}
        ).json()
        assert body["rows"] == []
        assert body["refused"] is True
        assert "insufficient" in body["message"].lower()

    def test_at_exactly_min_n_it_answers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query",
            lambda payload, timeout=20.0: [{"deal_points.n": 5}],
        )
        body = client.post(
            "/agent/run-selection", json={"measures": ["deal_points.n"], "dimensions": []}
        ).json()
        assert body["refused"] is False

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

from typing import Any, ClassVar

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
        },
        # The real vocabulary has TWO namespaces and this fixture had one, so every gate test
        # ran in a world where `comparable_deals.n` did not exist — which is precisely the
        # measure the gate was blind to. A fixture narrower than production cannot fail the
        # way production does.
        {
            "name": "comparable_deals",
            "measures": [
                {
                    "name": "comparable_deals.n",
                    "title": "Agreements",
                    "type": "count",
                    "description": "one row per merger agreement",
                }
            ],
            "dimensions": [
                {
                    "name": "comparable_deals.target_name",
                    "title": "Target",
                    "type": "string",
                    "description": "d",
                },
                {
                    "name": "comparable_deals.consideration_type",
                    "title": "Consideration",
                    "type": "string",
                    "description": "d",
                },
                {
                    "name": "comparable_deals.is_inferred_industry",
                    "title": "Industry inferred",
                    "type": "boolean",
                    "description": "d",
                },
            ],
        },
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


class TestTheGateFindsTheCountAtAll:
    """The existing gate tests all hand the mock `[{"deal_points.n": 3}]` — one row, keyed
    with the exact string the implementation hardcodes. They prove `3 < 5` evaluates
    correctly, which was never in doubt, and prove nothing about whether the gate locates a
    number in the first place. Every case below is a real Cube response shape that the gate
    was blind to.
    """

    @staticmethod
    def _run(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> dict:
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query", lambda payload, timeout=20.0: rows
        )
        return client.post(
            "/agent/run-selection",
            json={"measures": ["comparable_deals.n"], "dimensions": []},
        ).json()

    def test_a_slice_of_one_on_the_other_namespace_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The k-anonymity hole. `comparable_deals` rows are keyed `comparable_deals.n`, so a
        gate hardcoded to `deal_points.n` read None and skipped the comparison entirely —
        serving target and acquirer names on a slice of one."""
        body = self._run(
            monkeypatch,
            [{"comparable_deals.n": 1, "comparable_deals.target_name": "EATON VANCE CORP."}],
        )
        assert body["refused"] is True, "a single agreement must never be characterized"
        assert body["n"] == 1
        assert body["rows"] == []

    def test_a_thin_cell_below_the_first_row_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A grouped result is a set of cells and the gate protects each one. Reading rows[0]
        served `Mixed Cash/Stock: Election  n=3` in row four behind a fat first row."""
        body = self._run(
            monkeypatch,
            [
                {"comparable_deals.n": 89},
                {"comparable_deals.n": 39},
                {"comparable_deals.n": 21},
                {"comparable_deals.n": 3},
            ],
        )
        assert body["refused"] is True
        assert body["n"] == 3, "the gate must report the cell that failed, not the first one"

    def test_it_gates_on_agreements_not_on_answers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`deal_points.n` counts ANSWERS: healthcare is 26 agreements but 2,245 answers. A
        gate reading the inflated measure clears a threshold of 5 on a slice of one."""
        body = self._run(monkeypatch, [{"comparable_deals.n": 1, "deal_points.n": 89}])
        assert body["refused"] is True
        assert body["n"] == 1, "89 answers about one agreement is still one agreement"

    def test_an_empty_slice_is_refused_not_reported_as_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zero rows read as 'we have no comparable deals'. n=0 is below any threshold and
        must refuse like any other thin slice."""
        body = self._run(monkeypatch, [{"comparable_deals.n": 0}])
        assert body["refused"] is True
        assert body["n"] == 0

    def test_a_median_on_its_own_still_claims_no_denominator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one case the old behaviour got right, pinned so the fix cannot regress it:
        no count selected means there is no denominator to gate on and none is claimed."""
        body = self._run(monkeypatch, [{"deal_points.median_numeric_value": 4.0}])
        assert body["refused"] is False
        assert body["n"] is None


class TestRealCubeResponseShapes:
    """Cube serialises every measure as a STRING — a live rollup returns
    `{"comparable_deals.n": "89"}`, never `89`. Every mock in this file predating these tests
    hands the route an int, so the suite has been exercising a response shape the semantic
    layer does not produce. That is the same defect that hid the gate bug: a fixture written
    from the implementation's point of view rather than the dependency's.
    """

    @staticmethod
    def _run(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> dict:
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query", lambda payload, timeout=20.0: rows
        )
        return client.post(
            "/agent/run-selection",
            json={"measures": ["comparable_deals.n"], "dimensions": []},
        ).json()

    def test_a_string_count_still_gates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The shape Cube actually returns."""
        body = self._run(monkeypatch, [{"comparable_deals.n": "3"}])
        assert body["refused"] is True
        assert body["n"] == 3, "n must be an int in the response even though Cube sent a string"

    def test_a_string_count_above_the_threshold_answers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = self._run(monkeypatch, [{"comparable_deals.n": "89"}])
        assert body["refused"] is False
        assert body["n"] == 89

    def test_a_null_measure_value_is_not_read_as_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cube returns null for a measure with nothing to aggregate. Coercing that to 0 would
        manufacture a refusal for a slice whose size is simply unknown — a different claim."""
        body = self._run(monkeypatch, [{"comparable_deals.n": None}])
        assert body["n"] is None
        assert body["refused"] is False

    def test_a_row_missing_the_measure_entirely_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dimension-only row. The gate must skip it rather than raise, because a 500 here
        reads to the caller exactly like the semantic layer being down."""
        body = self._run(
            monkeypatch,
            [{"comparable_deals.target_name": "EATON VANCE CORP."}, {"comparable_deals.n": "7"}],
        )
        assert body["n"] == 7
        assert body["refused"] is False


class TestGrainIsNotInterchangeable:
    """`comparable_deals.n` counts agreements; `deal_points.n` counts answers. On healthcare
    that is 26 versus 2,245 — the same slice, differing by ~89x, because a row means something
    different in each namespace. Nothing in the suite pinned that, so treating one as a
    substitute for the other looked like a cleanup rather than a regression.
    """

    def test_the_smaller_count_wins_so_the_gate_cannot_be_walked_past(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query",
            lambda payload, timeout=20.0: [{"comparable_deals.n": "1", "deal_points.n": "89"}],
        )
        body = client.post(
            "/agent/run-selection",
            json={"measures": ["comparable_deals.n"], "dimensions": []},
        ).json()
        assert body["n"] == 1, "89 answers about a single agreement is still a single agreement"
        assert body["refused"] is True


class TestWhatActuallyReachesCube:
    """The payload is the contract with the semantic layer. Anything the route adds, drops or
    rewrites between validation and `cube_query` is unvalidated by construction — validation
    ran on the selection, not on whatever was sent.
    """

    @staticmethod
    def _capture(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> list[dict]:
        sent: list[dict] = []
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())

        def spy(payload: dict, timeout: float = 20.0) -> list[dict[str, object]]:
            sent.append(payload)
            return rows

        monkeypatch.setattr("explorer.api.run_selection.cube_query", spy)
        return sent

    def test_the_payload_carries_the_selection_and_a_limit_and_nothing_else(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = self._capture(monkeypatch, [{"comparable_deals.n": "40"}])
        client.post(
            "/agent/run-selection",
            json={
                "measures": ["comparable_deals.n"],
                "dimensions": ["comparable_deals.target_name"],
                "filters": [
                    {
                        "member": "comparable_deals.consideration_type",
                        "operator": "equals",
                        "values": ["All Cash"],
                    }
                ],
            },
        )
        assert set(sent[0]) == {"measures", "dimensions", "filters", "limit"}
        assert sent[0]["measures"] == ["comparable_deals.n"]
        assert sent[0]["dimensions"] == ["comparable_deals.target_name"]
        assert sent[0]["filters"][0]["values"] == ["All Cash"]

    def test_the_response_echoes_the_payload_that_was_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The resolved-query display is the designed catch for a wrong selection, and it is
        only worth anything if it shows what was SENT rather than what was asked for."""
        sent = self._capture(monkeypatch, [{"comparable_deals.n": "40"}])
        body = client.post(
            "/agent/run-selection",
            json={"measures": ["comparable_deals.n"], "dimensions": []},
        ).json()
        assert body["query"] == sent[0]

    def test_a_filter_value_shaped_like_an_injection_travels_as_a_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Filter VALUES cannot be enum-constrained the way names are, so a hostile string is
        always reachable. It must arrive at Cube as data in the payload — never spliced into
        anything — and the assertion is that it survives byte-identical."""
        hostile = "All Cash'); DROP TABLE deal_points; --"
        sent = self._capture(monkeypatch, [{"comparable_deals.n": "0"}])
        client.post(
            "/agent/run-selection",
            json={
                "measures": ["comparable_deals.n"],
                "dimensions": [],
                "filters": [
                    {
                        "member": "comparable_deals.consideration_type",
                        "operator": "equals",
                        "values": [hostile],
                    }
                ],
            },
        )
        assert sent[0]["filters"][0]["values"] == [hostile]


class TestCubeBeingDownIsNotAnEmptyAnswer:
    def test_an_unreachable_cube_is_503_not_zero_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ "The semantic layer is down" and "this slice is empty" are different statements and
        only one of them is about the corpus. Collapsing them teaches a reader to distrust
        every empty result they ever see."""
        from explorer.api.cube_client import CubeUnavailable

        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())

        def down(payload: dict, timeout: float = 20.0) -> list[dict[str, object]]:
            raise CubeUnavailable("connection refused")

        monkeypatch.setattr("explorer.api.run_selection.cube_query", down)
        response = client.post(
            "/agent/run-selection",
            json={"measures": ["comparable_deals.n"], "dimensions": []},
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] != "validation_error"


class TestAThinCellIsSuppressedNotFatal:
    """Refusing a whole grouped result because one tail cell is thin is the aggressive reading
    and it breaks legitimate work: the consideration split is 89/39/21/3, and killing all four
    to protect the fourth answers nothing. Published deal-points studies report the categories
    with enough sample and say the rest were too thin; this does the same.

    The cost, stated rather than hidden: a reader can infer that a suppressed cell exists and
    is small. That is inherent to publishing a suppression notice at all, and it is the trade
    every disclosure-control system makes.
    """

    @staticmethod
    def _grouped(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> dict:
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query", lambda payload, timeout=20.0: rows
        )
        return client.post(
            "/agent/run-selection",
            json={
                "measures": ["comparable_deals.n"],
                "dimensions": ["comparable_deals.consideration_type"],
            },
        ).json()

    #: the real consideration split, which is why the tail cell is the interesting one
    ROWS: ClassVar[list[dict[str, object]]] = [
        {"comparable_deals.consideration_type": "All Cash", "comparable_deals.n": "89"},
        {"comparable_deals.consideration_type": "All Stock", "comparable_deals.n": "39"},
        {"comparable_deals.consideration_type": "Mixed Cash/Stock", "comparable_deals.n": "21"},
        {
            "comparable_deals.consideration_type": "Mixed Cash/Stock: Election",
            "comparable_deals.n": "3",
        },
    ]

    def test_the_healthy_cells_are_still_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = self._grouped(monkeypatch, self.ROWS)
        assert body["refused"] is False
        assert len(body["rows"]) == 3

    def test_the_thin_cell_is_gone_from_the_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = self._grouped(monkeypatch, self.ROWS)
        values = [r["comparable_deals.consideration_type"] for r in body["rows"]]
        assert "Mixed Cash/Stock: Election" not in values
        assert all(int(r["comparable_deals.n"]) >= 5 for r in body["rows"])

    def test_the_suppression_is_declared_not_silent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Quietly dropping a row is worse than refusing: the reader believes they are looking
        at the whole distribution and the denominators no longer add up."""
        body = self._grouped(monkeypatch, self.ROWS)
        assert body["suppressed"] == 1
        assert "suppressed" in (body["message"] or "").lower()
        assert "5" in (body["message"] or ""), "the message must name the threshold"

    def test_n_reports_the_smallest_cell_that_survived(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = self._grouped(monkeypatch, self.ROWS)
        assert body["n"] == 21

    def test_when_every_cell_is_thin_it_refuses_rather_than_returning_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty row list with refused=false is the shape this endpoint exists to avoid."""
        body = self._grouped(
            monkeypatch,
            [
                {"comparable_deals.consideration_type": "a", "comparable_deals.n": "2"},
                {"comparable_deals.consideration_type": "b", "comparable_deals.n": "1"},
            ],
        )
        assert body["refused"] is True
        assert body["rows"] == []

    def test_an_ungrouped_thin_result_still_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Suppression only makes sense per cell. A single aggregate has no healthy remainder
        to return, so it refuses exactly as before."""
        monkeypatch.setattr("explorer.api.run_selection.fetch_vocabulary", lambda: _vocab())
        monkeypatch.setattr(
            "explorer.api.run_selection.cube_query",
            lambda payload, timeout=20.0: [{"comparable_deals.n": "3"}],
        )
        body = client.post(
            "/agent/run-selection",
            json={"measures": ["comparable_deals.n"], "dimensions": []},
        ).json()
        assert body["refused"] is True
        assert body["suppressed"] == 0

"""`POST /deal-terms` — the rollup over a selected set (#21).

This replaces the comparison chart an associate builds by hand from eight agreements, so the
thing under test is not really the arithmetic. It is the *reporting discipline*: that a small
sample renders as "6 of 8" and never as "75%", that a deal point nobody negotiated is still a
visible row, and that every figure arrives with the denominator it was computed against.

Cube is stubbed for the rendering rules so they run in the no-key gate with nothing up; the
`needs_corpus` class at the bottom puts the same endpoint against real Cube.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
import pytest
from explorer.api import deal_terms as module
from explorer.api.cube_client import CubeUnavailable
from explorer.api.main import app
from fastapi.testclient import TestClient

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

NAME = "deal_points.deal_point_name"
N = "deal_points.n"
PRESENT = "deal_points.present_count"
POSITION = "deal_points.position"
NUMERIC_N = "deal_points.numeric_n"
MEDIAN = "deal_points.median_numeric_value"
P25 = "deal_points.p25_numeric_value"
P75 = "deal_points.p75_numeric_value"

EIGHT = [f"contract_{i}" for i in range(1, 9)]


class StubCube:
    """Answers by the shape of the query, and records every payload."""

    def __init__(self, rollup: list[dict[str, Any]], vocabulary: list[str] | None = None) -> None:
        self.rollup = rollup
        self.vocabulary = vocabulary if vocabulary is not None else [r[NAME] for r in rollup]
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
        self.payloads.append(payload)
        dimensions = payload.get("dimensions") or []
        measures = payload.get("measures") or []
        if POSITION in dimensions:
            return [
                {NAME: r[NAME], POSITION: r.get("_position", "Yes"), N: r[PRESENT]}
                for r in self.rollup
                if r[PRESENT]
            ]
        if not measures:  # the deal-point vocabulary
            return [{NAME: name} for name in self.vocabulary]
        return self.rollup


def rollup_row(name: str, n: int, present: int, **extra: Any) -> dict[str, Any]:
    return {NAME: name, N: n, PRESENT: present, **extra}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _stub(monkeypatch: pytest.MonkeyPatch, cube: StubCube) -> StubCube:
    monkeypatch.setattr(module, "cube_query", cube)
    return cube


def _row(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in body["rows"] if r["deal_point_name"] == name)


class TestTheCountVsPercentageRule:
    """The rule the whole tab exists to respect, asserted at its exact edge."""

    def test_below_the_threshold_it_renders_a_count(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = _row(body, "Fiduciary exception")
        assert row["display"] == "6 of 8"
        assert row["display_kind"] == "count"
        assert "%" not in row["display"]

    def test_at_the_threshold_it_switches_to_a_percentage(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exactly at the boundary, not one past it — off-by-one here is a silent policy change."""
        threshold = module.settings.percentage_threshold
        _stub(
            monkeypatch,
            StubCube([rollup_row("Fiduciary exception", n=threshold, present=threshold // 2)]),
        )
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = _row(body, "Fiduciary exception")
        assert row["display_kind"] == "percentage"
        assert row["display"].endswith("%")

    def test_one_below_the_threshold_is_still_a_count(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        threshold = module.settings.percentage_threshold
        _stub(
            monkeypatch, StubCube([rollup_row("Fiduciary exception", n=threshold - 1, present=5)])
        )
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert _row(body, "Fiduciary exception")["display_kind"] == "count"

    def test_the_threshold_in_force_is_reported(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reader must be able to see which rule produced the rendering."""
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert body["percentage_threshold"] == module.settings.percentage_threshold

    def test_a_percentage_never_appears_anywhere_below_the_threshold(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(
            monkeypatch,
            StubCube(
                [
                    rollup_row("A", n=8, present=6),
                    rollup_row("B", n=3, present=3),
                    rollup_row("C", n=8, present=0),
                ]
            ),
        )
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert all("%" not in r["display"] for r in body["rows"])


class TestAbsenceIsAFinding:
    def test_a_deal_point_no_matter_negotiated_is_a_row_not_an_omission(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(
            monkeypatch,
            StubCube(
                [rollup_row("Fiduciary exception", n=8, present=6)],
                vocabulary=["Fiduciary exception", "Ticking fee"],
            ),
        )
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        absent = _row(body, "Ticking fee")
        assert absent["display"] == "0 of 8"
        assert absent["answered_n"] == 0

    def test_present_but_never_agreed_reads_zero_of_the_answered_set(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Distinct from the above: here every matter has an answer and every answer is 'No'."""
        _stub(monkeypatch, StubCube([rollup_row("Ticking fee", n=8, present=0)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert _row(body, "Ticking fee")["display"] == "0 of 8"


class TestEveryFigureCarriesItsDenominator:
    def test_each_row_reports_the_answered_set_it_was_computed_over(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=6, present=4)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = _row(body, "Fiduciary exception")
        # 6, not 8: two of the selected matters have no labelled answer for this deal point
        assert row["answered_n"] == 6
        assert row["present_count"] == 4
        assert body["selection_n"] == 8

    def test_a_numeric_deal_point_carries_median_p25_p75_and_its_own_n(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(
            monkeypatch,
            StubCube(
                [
                    rollup_row(
                        "Ticking fee",
                        n=8,
                        present=6,
                        **{NUMERIC_N: 5, MEDIAN: 4.0, P25: 3.0, P75: 6.5},
                    )
                ]
            ),
        )
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        numeric = _row(body, "Ticking fee")["numeric"]
        assert numeric == {"numeric_n": 5, "median": 4.0, "p25": 3.0, "p75": 6.5}

    def test_a_non_numeric_deal_point_has_no_numeric_block(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not a zero, not an empty object: numeric statistics do not apply to it at all."""
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert _row(body, "Fiduciary exception")["numeric"] is None

    def test_no_mean_is_ever_returned(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one `type: avg` measure exists to demonstrate divergence, not to be served."""
        cube = _stub(monkeypatch, StubCube([rollup_row("Ticking fee", n=8, present=6)]))
        client.post("/deal-terms", json={"matter_ids": EIGHT})
        requested = {m for p in cube.payloads for m in (p.get("measures") or [])}
        assert not any("mean" in m for m in requested)


class TestTheSelectionReachesCube:
    def test_the_selected_matter_ids_are_the_filter(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cube = _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        client.post("/deal-terms", json={"matter_ids": EIGHT})
        rollup = next(p for p in cube.payloads if PRESENT in (p.get("measures") or []))
        matter_filter = next(f for f in rollup["filters"] if f["member"] == "deal_points.matter_id")
        assert matter_filter["operator"] == "equals"
        assert matter_filter["values"] == EIGHT

    def test_an_empty_selection_is_rejected_rather_than_rolled_up_over_the_corpus(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unfiltered rollup would silently answer about all 152 matters."""
        _stub(monkeypatch, StubCube([]))
        assert client.post("/deal-terms", json={"matter_ids": []}).status_code == 422


class TestScopeIsStated:
    def test_the_response_says_these_are_public_comparables(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tab must not read as the firm's own negotiating history."""
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert "public" in body["scope_note"].lower()
        assert "not" in body["scope_note"].lower()


class TestMinNRefusal:
    """The single most important behavior in the product (#23): min_n does three jobs at once
    — statistical honesty, extraction-confidence gating, and k-anonymity. An analyst who
    narrows a filter to n=1 has extracted one client's negotiated term through the aggregate
    layer, around the ethical wall, without ever retrieving a document. Below min_n, this
    endpoint must refuse — including in the "count" form ("1 of 1"), which is exactly as
    identifying as a raw document would be.
    """

    def test_a_selection_below_min_n_is_refused_not_answered(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cube = _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=2, present=1)]))
        two = EIGHT[:2]
        body = client.post("/deal-terms", json={"matter_ids": two}).json()
        assert body["refused"] is True
        assert body["rows"] == []
        # no cube query at all: the refusal happens before any number could be computed
        assert cube.payloads == []

    def test_the_refusal_states_the_actual_n_and_the_threshold(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(monkeypatch, StubCube([]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT[:3]}).json()
        assert body["refusal"]["n"] == 3
        assert body["refusal"]["threshold"] == module.settings.min_n
        assert "n=3" in body["refusal"]["message"]
        assert str(module.settings.min_n) in body["refusal"]["message"]

    def test_a_selection_at_exactly_min_n_is_answered(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        threshold = module.settings.min_n
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=threshold, present=1)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT[:threshold]}).json()
        assert body["refused"] is False
        assert body["rows"]

    def test_refusal_cannot_be_bypassed_by_a_direct_api_call(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The gate is server-side. There is no client flag, header, or parameter that
        reaches this endpoint and turns it off — the request shape offers none."""
        _stub(monkeypatch, StubCube([rollup_row("Ticking fee", n=1, present=1)]))
        response = client.post(
            "/deal-terms",
            json={"matter_ids": ["contract_1"], "bypass_min_n": True, "admin": True},
        )
        assert response.json()["refused"] is True

    def test_refused_response_is_not_shaped_like_an_empty_result(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Distinct response shape, not merely an empty rows list — a client checking only
        `rows.length === 0` must not silently render this as "no terms found"."""
        _stub(monkeypatch, StubCube([]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT[:1]}).json()
        assert "refused" in body
        assert "refusal" in body
        assert body["refusal"] is not None


class TestExtractionConfidenceGate:
    """The second gate #23 requires: a deal point whose calibrated extraction accuracy is below
    threshold must not be aggregated. MAUD's own labels are gold (never gated); this applies
    only to extractor output, and no extractor has run a calibration pass yet (#28) — so the
    mechanism is exercised here via an injected confidence source rather than real numbers,
    which do not exist yet. Fabricating a plausible accuracy would violate the no-fabricated-
    numbers rule; "not yet measured" is why this gate is currently inert in production.
    """

    def test_a_low_confidence_deal_point_is_excluded_with_its_own_message(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(monkeypatch, StubCube([rollup_row("Extractor field", n=8, present=5)]))
        monkeypatch.setattr(module, "confidence_lookup", lambda name: 0.3)
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = _row(body, "Extractor field")
        assert row["display_kind"] == "low_confidence"
        assert row["display"] == "not characterized"
        assert "confidence" in row["gate_note"].lower()

    def test_a_deal_point_with_no_measured_confidence_is_not_gated(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default: nothing has been calibrated yet, so nothing is excluded by this gate."""
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        monkeypatch.setattr(module, "confidence_lookup", lambda name: None)
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = _row(body, "Fiduciary exception")
        assert row["display_kind"] == "count"

    def test_the_confidence_threshold_is_reported(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub(monkeypatch, StubCube([rollup_row("Fiduciary exception", n=8, present=6)]))
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert body["min_extraction_confidence"] == module.settings.min_extraction_confidence


class TestDrillThroughRefusal:
    """Drill-through is the sharper k-anonymity risk of the two endpoints: it returns a named
    matter's actual clause text. If the rollup refuses at n=3 but drill does not, the gate is
    decorative — an analyst just clicks through the row that was refused."""

    def test_drill_refuses_below_min_n_without_touching_the_database(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drill reads Postgres directly (#20/#21), not Cube — the refusal must happen before
        that query runs, or the DB is asked for a named client's clause text regardless."""
        called = []
        monkeypatch.setattr(
            module,
            "_run_drill_query",
            lambda name, ids: called.append((name, ids)) or [],
        )
        response = client.post(
            "/deal-terms/drill",
            json={"matter_ids": ["contract_1", "contract_2"], "deal_point_name": "Ticking fee"},
        )
        body = response.json()
        assert body["refused"] is True
        assert called == []


class TestCubeFailureIsNotAnEmptyRollup:
    def test_an_unavailable_cube_is_a_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
            raise CubeUnavailable("Cube did not answer")

        monkeypatch.setattr(module, "cube_query", boom)
        response = client.post("/deal-terms", json={"matter_ids": EIGHT})
        assert response.status_code == 503


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM deal_points").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


@pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
class TestAgainstRealCube:
    def test_a_real_selection_rolls_up_with_counts_not_percentages(
        self, client: TestClient
    ) -> None:
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert body["selection_n"] == 8
        assert body["rows"], "a real 8-matter selection must produce rows"
        # 8 is far below the threshold, so nothing in this response may be a percentage
        assert all("%" not in r["display"] for r in body["rows"])

    def test_the_rollup_only_counts_the_selected_matters(self, client: TestClient) -> None:
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        assert all(r["answered_n"] <= 8 for r in body["rows"])

    def test_drill_through_returns_the_matters_behind_a_row(self, client: TestClient) -> None:
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = next(r for r in body["rows"] if r["present_count"] > 0)
        drill = client.post(
            "/deal-terms/drill",
            json={"matter_ids": EIGHT, "deal_point_name": row["deal_point_name"]},
        ).json()
        assert len(drill["matters"]) == row["answered_n"]
        assert all(m["matter_id"] in EIGHT for m in drill["matters"])
        assert all(m["position"] for m in drill["matters"])

    def test_drill_through_reaches_the_clause_language_itself(self, client: TestClient) -> None:
        """Demo script 2 beat 5: the actual clause language, with source file and offsets.

        Returning the matter id and the position only is a list of pointers, not a
        drill-through — the associate still has to go and open eight agreements.
        """
        from explorer.ingest.maud_corpus import corpus_available

        if not corpus_available():
            pytest.skip("MAUD corpus not downloaded")

        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = next(r for r in body["rows"] if r["present_count"] > 0)
        drill = client.post(
            "/deal-terms/drill",
            json={"matter_ids": EIGHT, "deal_point_name": row["deal_point_name"]},
        ).json()

        located = [m for m in drill["matters"] if m["source_span_start"] is not None]
        assert located, "this deal point should be traceable in at least one agreement"
        for m in located:
            assert m["source_file"].endswith(".txt")
            assert m["source_span_end"] > m["source_span_start"]
            assert m["clause_text"]

    def test_drill_through_clause_text_is_the_exact_slice_of_the_agreement(
        self, client: TestClient
    ) -> None:
        from explorer.ingest.maud_corpus import CONTRACTS_DIR, corpus_available

        if not corpus_available():
            pytest.skip("MAUD corpus not downloaded")

        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = next(r for r in body["rows"] if r["present_count"] > 0)
        drill = client.post(
            "/deal-terms/drill",
            json={"matter_ids": EIGHT, "deal_point_name": row["deal_point_name"]},
        ).json()

        # Two shapes now, and the response says which: a clause-scale span comes back whole,
        # a document-scale one comes back as the opening excerpt of that same slice. Both must
        # be characters actually taken from the agreement at the recorded offset — the point of
        # the assertion is that no text is ever synthesised.
        for m in (x for x in drill["matters"] if x["clause_text"]):
            raw = (CONTRACTS_DIR / f"{m['matter_id']}.txt").read_text(
                encoding="utf-8", errors="replace"
            )
            span = raw[m["source_span_start"] : m["source_span_end"]]
            assert m["span_chars"] == m["source_span_end"] - m["source_span_start"]
            if m["is_excerpt"]:
                assert span.startswith(m["clause_text"])
                assert len(m["clause_text"]) < len(span)
            else:
                assert m["clause_text"] == span

    def test_an_untraceable_answer_says_so_rather_than_going_blank(
        self, client: TestClient
    ) -> None:
        """Same rule as the matter card: no span means a stated reason, never invented text."""
        body = client.post("/deal-terms", json={"matter_ids": EIGHT}).json()
        row = next(r for r in body["rows"] if r["present_count"] > 0)
        drill = client.post(
            "/deal-terms/drill",
            json={"matter_ids": EIGHT, "deal_point_name": row["deal_point_name"]},
        ).json()
        for m in drill["matters"]:
            assert m["clause_text"] is not None or m["text_unavailable"]

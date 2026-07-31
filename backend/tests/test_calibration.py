"""Calibration grading (#28) — the pure, offline half.

`record_predictions()` is the only thing here that calls out (needs_key, exercised for real to
produce the committed `docs/eval/calibration_predictions.json`). `wilson_interval` and `grade`
are pure and are what actually has to be correct: a wrong CI formula silently mislabels a
deal point as reportable when it is not, exactly the failure #23's threshold exists to prevent
one level upstream.

Runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import json
import os

import psycopg
import pytest
from explorer.evals.calibration import grade, wilson_interval

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM deal_points").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


class TestWilsonInterval:
    def test_a_perfect_score_has_a_ci_that_does_not_touch_100_percent_at_small_n(self) -> None:
        """10 of 10 correct is not proof of 100% accuracy — the interval must say so."""
        low, high = wilson_interval(10, 10)
        assert low < 1.0
        assert high == 1.0

    def test_zero_correct_of_zero_trials_is_not_a_division_error(self) -> None:
        assert wilson_interval(0, 0) == (0.0, 0.0)

    def test_the_interval_widens_as_n_shrinks(self) -> None:
        low_small, high_small = wilson_interval(8, 10)
        low_large, high_large = wilson_interval(80, 100)
        assert (high_small - low_small) > (high_large - low_large)

    def test_bounds_never_leave_the_unit_interval(self) -> None:
        for correct, n in [(0, 5), (5, 5), (3, 5)]:
            low, high = wilson_interval(correct, n)
            assert 0.0 <= low <= high <= 1.0


class TestGradeIsOfflineAndPerDealPoint:
    @pytest.fixture
    def fixture_predictions(self, tmp_path):  # type: ignore[no-untyped-def]
        # Two deal points, deliberately different accuracy, against real corpus positions for
        # a couple of holdout matters so `actual_positions` has something real to compare to.
        preds = [
            {
                "matter_id": "contract_4",
                "deal_point_name": "Announcement, pendency or consummation of deal (Y/N)",
                "predicted_position": "definitely-wrong-value",
                "quoted_text": None,
                "span_start": None,
                "span_end": None,
                "tokens": 100,
            },
            {
                "matter_id": "contract_8",
                "deal_point_name": "Announcement, pendency or consummation of deal (Y/N)",
                "predicted_position": "definitely-wrong-value",
                "quoted_text": None,
                "span_start": None,
                "span_end": None,
                "tokens": 100,
            },
        ]
        path = tmp_path / "predictions.json"
        path.write_text(json.dumps(preds))
        return path

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_every_result_carries_n_and_a_ci_not_a_bare_percentage(
        self, fixture_predictions
    ) -> None:  # type: ignore[no-untyped-def]
        summary = grade(predictions_path=fixture_predictions)
        assert summary["results"]
        for r in summary["results"]:
            assert r.n > 0
            assert r.ci_low <= r.accuracy <= r.ci_high

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_a_deal_point_with_a_low_ci_bound_is_marked_not_reportable(
        self, fixture_predictions
    ) -> None:  # type: ignore[no-untyped-def]
        """Both predictions are wrong on purpose, so the lower bound must sit at/near 0 — far
        below any sane min_extraction_confidence — and reportable must say so."""
        summary = grade(predictions_path=fixture_predictions)
        r = summary["results"][0]
        assert r.accuracy == 0.0
        assert r.reportable is False

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_the_threshold_in_force_is_reported(self, fixture_predictions) -> None:  # type: ignore[no-untyped-def]
        from explorer.api.settings import settings

        summary = grade(predictions_path=fixture_predictions)
        assert summary["min_extraction_confidence"] == settings.min_extraction_confidence

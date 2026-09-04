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
from explorer.evals.calibration import grade, score, wilson_interval

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


DP = "Announcement, pendency or consummation of deal (Y/N)"


def _prediction(matter_id: str, position: str, deal_point: str = DP) -> dict:  # type: ignore[type-arg]
    return {
        "matter_id": matter_id,
        "deal_point_name": deal_point,
        "predicted_position": position,
        "quoted_text": None,
        "span_start": None,
        "span_end": None,
        "tokens": 10,
    }


# 5 rows, one of them wrong: the shape the AC's "moves by exactly 1/n" is stated against.
PREDICTIONS = [
    _prediction("contract_1", "Yes"),
    _prediction("contract_2", "Yes"),
    _prediction("contract_3", "Yes"),
    _prediction("contract_4", "Yes"),
    _prediction("contract_5", "No"),
]
ACTUAL = {(f"contract_{i}", DP): "Yes" for i in range(1, 6)}


class TestHumanLabelsAreReadBackIntoTheScore:
    """#41 — the Label tab wrote rows nothing read. `score` is the pure half of `grade`: it
    takes the predictions, MAUD's gold, and whatever humans labelled, so the substitution rule
    is testable without a database and without a key."""

    def test_with_no_labels_the_score_is_the_extractor_alone(self) -> None:
        summary = score(PREDICTIONS, ACTUAL, {})
        assert summary["labels_applied"] == 0
        r = summary["results"][0]
        assert (r.correct, r.n) == (4, 5)
        assert r.accuracy == r.accuracy_before == 0.8

    def test_a_labelled_disagreement_flips_a_graded_row_and_moves_accuracy_by_one_over_n(
        self,
    ) -> None:
        labels = {("contract_5", DP): "Yes"}
        summary = score(PREDICTIONS, ACTUAL, labels)

        r = summary["results"][0]
        assert r.correct_before == 4
        assert r.correct == 5
        assert r.labels_applied == 1
        assert r.accuracy - r.accuracy_before == pytest.approx(1 / r.n)
        assert summary["accuracy_after"] - summary["accuracy_before"] == pytest.approx(1 / 5)

    def test_a_wrong_human_label_moves_the_score_down_by_one_over_n(self) -> None:
        """The loop is not a ratchet. A reviewer who mistypes degrades the measurement, and
        the grader must show that rather than quietly keeping the better number."""
        summary = score(PREDICTIONS, ACTUAL, {("contract_1", DP): "s"})
        r = summary["results"][0]
        assert r.accuracy_before - r.accuracy == pytest.approx(1 / r.n)

    def test_a_label_agreeing_with_the_prediction_counts_as_applied_but_moves_nothing(
        self,
    ) -> None:
        summary = score(PREDICTIONS, ACTUAL, {("contract_1", DP): "Yes"})
        assert summary["labels_applied"] == 1
        assert summary["labels_differing"] == 0
        r = summary["results"][0]
        assert r.accuracy == r.accuracy_before

    def test_a_label_for_a_row_that_was_never_predicted_is_ignored(self) -> None:
        summary = score(PREDICTIONS, ACTUAL, {("contract_99", DP): "Yes"})
        assert summary["labels_applied"] == 0
        assert summary["results"][0].accuracy == 0.8

    def test_the_confidence_interval_is_computed_on_the_post_label_score(self) -> None:
        """A CI carried over from the pre-label number would understate a corrected extractor
        exactly where #23's reportable gate reads it."""
        summary = score(PREDICTIONS, ACTUAL, {("contract_5", DP): "Yes"})
        r = summary["results"][0]
        assert (r.ci_low, r.ci_high) == tuple(round(x, 3) for x in wilson_interval(5, 5))

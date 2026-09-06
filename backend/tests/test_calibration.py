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
from dataclasses import asdict
from typing import ClassVar

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


ANNOUNCEMENT = "Announcement, pendency or consummation of deal (Y/N)"


@pytest.fixture
def wrong_predictions(tmp_path):  # type: ignore[no-untyped-def]
    """Two predictions, both deliberately wrong, for one real deal point."""
    preds = [
        {
            "matter_id": matter,
            "deal_point_name": ANNOUNCEMENT,
            "predicted_position": "definitely-wrong-value",
            "quoted_text": None,
            "span_start": None,
            "span_end": None,
            "model": "gpt-4o-mini",
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "tokens": 110,
            "cost_usd": 0.000021,
        }
        for matter in ("contract_4", "contract_8")
    ]
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps(preds))
    return path


class TestFullVocabularyCoverage:
    """#44: the calibration table has to cover the whole deal-point vocabulary, and has to be
    honest about the part of it that could not be measured. A deal point MAUD never answers on
    the holdout is not 0% accurate — it is unmeasured, and the two must not render alike."""

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_the_vocabulary_comes_from_the_data_not_a_hardcoded_list(self) -> None:
        from explorer.evals.calibration import deal_point_vocabulary

        vocabulary = deal_point_vocabulary()
        assert len(vocabulary) > 5  # the pre-#44 hardcoded slice
        assert vocabulary == sorted(vocabulary)

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_only_pairs_with_a_gold_label_are_scheduled(self) -> None:
        """Predicting a (matter, deal point) MAUD never answered would score as wrong against
        a label that does not exist — a fabricated error rate, paid for in real tokens."""
        from explorer.evals.calibration import SPLIT_FILE, holdout_pairs

        pairs = holdout_pairs()
        assert pairs
        holdout = set(json.loads(SPLIT_FILE.read_text())["holdout_matter_ids"])
        assert {m for m, _ in pairs} <= holdout
        with psycopg.connect(DSN) as conn:
            labelled = {
                (m, d)
                for m, d in conn.execute(
                    "SELECT matter_id, deal_point_name FROM deal_points WHERE matter_id = ANY(%s)",
                    (sorted(holdout),),
                ).fetchall()
            }
        assert set(pairs) <= labelled

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_an_unmeasured_deal_point_is_a_row_marked_unmeasured_not_a_zero(
        self, wrong_predictions
    ) -> None:  # type: ignore[no-untyped-def]
        summary = grade(
            predictions_path=wrong_predictions,
            vocabulary=[ANNOUNCEMENT, "A deal point nobody predicted"],
        )
        unmeasured = next(
            r for r in summary["results"] if r.deal_point_name == "A deal point nobody predicted"
        )
        assert unmeasured.n == 0
        assert unmeasured.measured is False
        assert unmeasured.accuracy is None
        assert unmeasured.reportable is False
        assert summary["vocabulary_size"] == 2
        assert summary["measured_deal_point_count"] == 1

    @pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
    def test_results_are_sorted_worst_first_with_unmeasured_last(self, wrong_predictions) -> None:  # type: ignore[no-untyped-def]
        """The Admin table's ordering is decided here, not in the UI, so the committed file and
        the screen cannot disagree about which deal point is the weakest."""
        summary = grade(
            predictions_path=wrong_predictions,
            vocabulary=["A deal point nobody predicted", ANNOUNCEMENT],
        )
        assert [r.measured for r in summary["results"]] == [True, False]


class TestRunCost:
    """#44 AC: token and dollar cost recorded alongside the results, measured."""

    def test_cost_sums_input_and_output_separately_across_predictions(self) -> None:
        from explorer.evals.calibration import run_cost

        predictions = [
            {"model": "gpt-4o-mini", "prompt_tokens": 3000, "completion_tokens": 100},
            {"model": "gpt-4o-mini", "prompt_tokens": 2000, "completion_tokens": 50},
        ]
        cost = run_cost(predictions)
        assert cost["call_count"] == 2
        assert cost["prompt_tokens"] == 5000
        assert cost["completion_tokens"] == 150
        assert cost["cost_usd"] == pytest.approx(5000 / 1e6 * 0.15 + 150 / 1e6 * 0.60)
        assert cost["cost_usd_per_call"] == pytest.approx(cost["cost_usd"] / 2)

    def test_an_empty_run_has_no_per_call_cost_rather_than_dividing_by_zero(self) -> None:
        from explorer.evals.calibration import run_cost

        assert run_cost([])["cost_usd_per_call"] is None


class TestResumeSkipsWhatIsAlreadyRecorded:
    """#44: a 1,704-call run dropped 325 pairs to rate limits on its first pass.

    Re-running the whole thing to recover them would pay twice for the 1,379 that landed. The
    resume path computes the difference and prices only the difference, which is also what
    makes the committed cost figure the cost of the *table*, not of one attempt at it.
    """

    def test_missing_pairs_are_the_scheduled_set_minus_the_recorded_one(self) -> None:
        from explorer.evals.calibration import missing_pairs

        scheduled = [("m1", "d1"), ("m1", "d2"), ("m2", "d1")]
        recorded = [{"matter_id": "m1", "deal_point_name": "d1"}]
        assert missing_pairs(scheduled, recorded) == [("m1", "d2"), ("m2", "d1")]

    def test_a_complete_run_has_nothing_left_to_do(self) -> None:
        from explorer.evals.calibration import missing_pairs

        scheduled = [("m1", "d1")]
        recorded = [{"matter_id": "m1", "deal_point_name": "d1"}]
        assert missing_pairs(scheduled, recorded) == []


@pytest.mark.needs_key
@pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
class TestOneRealCallIsPricedEndToEnd:
    """One real call, so the cost path is exercised against the API's own usage numbers rather
    than a fixture that agrees with itself.

    This is the check that made #44's full run affordable to authorise: measure one call, read
    its token split off `response.usage`, price it, multiply. It is `needs_key` and therefore
    out of the CI gate — CI must stay runnable with no key and no spend.
    """

    def test_a_real_prediction_reports_a_priced_token_split(self) -> None:
        from explorer.api.settings import settings
        from explorer.evals.calibration import ROOT, holdout_pairs, run_cost
        from explorer.evals.extract_deal_point import predict

        if not settings.has_openai_key or settings.openai_api_key is None:
            pytest.skip("no key")

        matter_id, deal_point = holdout_pairs()[0]
        with psycopg.connect(DSN) as conn:
            source_file = conn.execute(
                "SELECT source_file FROM matters WHERE id = %s", (matter_id,)
            ).fetchone()[0]
            allowed = sorted(
                {
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT position FROM deal_points WHERE deal_point_name = %s",
                        (deal_point,),
                    ).fetchall()
                }
            )
        text = (ROOT / "data" / source_file).read_text(encoding="utf-8", errors="replace")
        prediction = predict(matter_id, text, deal_point, allowed, settings.openai_api_key)

        assert prediction.prompt_tokens > 0
        assert prediction.completion_tokens > 0
        assert prediction.tokens == prediction.prompt_tokens + prediction.completion_tokens
        assert prediction.cost_usd > 0
        # The answer is decoded back to a real position, never left as the option id.
        assert prediction.predicted_position in allowed

        cost = run_cost([asdict(prediction)])
        assert cost["cost_usd"] == pytest.approx(prediction.cost_usd, rel=1e-3)
        assert cost["unpriced_call_count"] == 0


class TestIndexBuildingSurvivesARateLimit:
    """#58's first full attempt died here, not in the extraction loop.

    Embedding one holdout agreement's passages is ~226,000 tokens, and twenty of them
    back-to-back exceeded the org's 1,000,000 tokens-per-minute embedding limit:

        openai.RateLimitError: Error code: 429 - Rate limit reached for
        text-embedding-3-small ... on tokens per min (TPM): Limit 1000000, Used 958214

    The extraction loop already retried with jittered backoff for exactly this reason; index
    building had no such wrapper, so one 429 threw away the whole run. Retrying is also cheap:
    batches that already landed are in the cache, so only the failed remainder is re-requested.
    """

    def test_a_transient_failure_is_retried_and_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from explorer.evals import calibration

        attempts = {"n": 0}

        class Built:
            passages: ClassVar[list[object]] = []

        def flaky(text: str, cache: object) -> Built:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("429")
            return Built()

        monkeypatch.setattr(calibration, "PassageIndex", flaky)
        monkeypatch.setattr(calibration.time, "sleep", lambda _seconds: None)
        assert isinstance(calibration.build_passage_index("text", cache=None), Built)  # type: ignore[arg-type]
        assert attempts["n"] == 3

    def test_a_permanent_failure_raises_rather_than_returning_an_empty_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An index with no passages would silently send the model an empty contract, and the
        run would report an accuracy for a question nobody was asked."""
        from explorer.evals import calibration

        def always_fails(text: str, cache: object) -> None:
            raise RuntimeError("429")

        monkeypatch.setattr(calibration, "PassageIndex", always_fails)
        monkeypatch.setattr(calibration.time, "sleep", lambda _seconds: None)
        with pytest.raises(RuntimeError):
            calibration.build_passage_index("text", cache=None)  # type: ignore[arg-type]

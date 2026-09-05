"""Committed artefacts behind the Trust tab (#54).

Every figure on Trust is read from a file a command produced, never recomputed when someone
opens the tab. Two reasons, and the second is the one that matters: a number recomputed per
request can drift from the report committed beside it, and then the tab and the repo disagree
with no way to tell which ran. The whole argument of the tab is that a sceptical reader can
check it.

The measure-selection scores were the gap. They existed as prose in
`docs/results/measure-selection.md` and as a dict printed to a terminal, so the only way to put
them on screen was to grade at request time. `write_summary` writes them as JSON beside the
markdown, from the same `run()` the report already uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from explorer.api.main import app
from explorer.evals.measure_selection import SUMMARY_FILE, run, write_summary
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestTheSummaryIsCommitted:
    def test_the_artefact_exists_in_the_repo(self) -> None:
        assert SUMMARY_FILE.is_file(), (
            "docs/results/measure-selection.json is not committed. Run "
            "`PYTHONPATH=backend python -m explorer.evals --only measure-selection`."
        )

    def test_it_carries_the_four_scores_the_tab_charts(self) -> None:
        summary = json.loads(SUMMARY_FILE.read_text())
        for key in (
            "measure_precision",
            "dimension_precision",
            "filter_exact_match_rate",
            "refusal_accuracy",
        ):
            assert isinstance(summary[key], (int, float)), key

    def test_the_committed_numbers_match_what_the_harness_computes_today(self) -> None:
        """The artefact is a snapshot of a deterministic grade over two committed files. If it
        drifts from `run()`, the committed file is stale and the tab is showing a number no
        current command reproduces."""
        committed = json.loads(SUMMARY_FILE.read_text())
        fresh = run()
        for key in (
            "case_count",
            "measure_precision",
            "dimension_precision",
            "filter_exact_match_rate",
            "refusal_accuracy",
        ):
            assert committed[key] == fresh[key], key

    def test_it_records_the_command_that_produced_it(self) -> None:
        """A number with no command beside it is unfalsifiable."""
        summary = json.loads(SUMMARY_FILE.read_text())
        assert "explorer.evals" in summary["command"]
        assert summary["generated_at"]

    def test_writing_it_drops_the_per_case_results(self, tmp_path: Path) -> None:
        """The per-case rows are already served by /agent/grading from the same fixtures. A
        second copy is a second thing to keep in sync."""
        out = tmp_path / "measure-selection.json"
        write_summary(run(), out_path=out)
        written = json.loads(out.read_text())
        assert "results" not in written
        assert written["refusal_accuracy"] == 0.2


class TestTheEndpointServesTheFile:
    def test_it_returns_the_committed_summary(self, client: TestClient) -> None:
        body = client.get("/admin/measure-selection").json()
        assert body["refusal_accuracy"] == 0.2
        assert body["measure_precision"] == 0.8
        assert body["dimension_precision"] == 0.692
        assert body["filter_exact_match_rate"] == 0.5

    def test_it_needs_no_database(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Trust's charts are files on disk. None of them is a query."""

        def forbidden(*args: object, **kwargs: object) -> None:
            raise AssertionError("a committed artefact was served from the database")

        monkeypatch.setattr("psycopg.connect", forbidden)
        assert client.get("/admin/measure-selection").status_code == 200


class TestTheChartedFiguresComeFromTheFiles:
    """The issue body quotes figures. Where a quoted figure and the committed file disagree,
    the file wins — these assertions are how that stays true after an eval re-run."""

    def test_calibration_counts(self) -> None:
        table = json.loads((ROOT / "docs" / "eval" / "calibration_accuracy.json").read_text())
        measured = [r for r in table["results"] if r["measured"]]
        assert table["vocabulary_size"] == 92
        assert len(measured) == 90
        # Two deal points the run never reached. They render "not measured", never 0.00.
        assert len([r for r in table["results"] if not r["measured"]]) == 2
        # "5 clear the gate" is the `reportable` flag — the Wilson LOWER bound over 0.70, not
        # the point estimate. 13 deal points have accuracy >= 0.70; only 5 clear it on the
        # bound. The chart's rule is drawn at 0.70 accuracy, so both counts are stated.
        assert table["reportable_count"] == 5
        assert len([r for r in measured if r["accuracy"] >= 0.70]) == 13
        assert len([r for r in measured if r["accuracy"] < 0.70]) == 77
        assert len([r for r in measured if r["accuracy"] == 0.0]) == 6

    def test_the_label_loop_artefact_is_internally_consistent(self) -> None:
        """The shipped artefact records zero decisions, and the numbers agree with that.

        This used to pin 6 applied and 569 -> 565 as *the finding*. Every one of those six rows
        turned out to be a development keystroke: a literal `s` from the Skip key, a half-typed
        `N`, and four reflexive `No`s on one deal point. They were graded against MAUD, so a
        keystroke became a published measurement. They are purged (#56), and the write path now
        validates against the deal point's vocabulary so it cannot happen again.

        What is asserted here is the property that outlives any particular data: the artefact is
        the single source for what the charts draw, and the delta it reports has to follow from
        the decisions it recorded rather than from a sentence someone wrote once.
        """
        labels = json.loads((ROOT / "docs" / "results" / "calibration-labels.json").read_text())
        assert labels["prediction_count"] == 1701
        assert labels["labels_differing"] <= labels["labels_applied"]
        assert 0 <= labels["correct_before"] <= labels["prediction_count"]
        assert 0 <= labels["correct_after"] <= labels["prediction_count"]
        if labels["labels_applied"] == 0:
            # nothing was substituted, so nothing can have moved
            assert labels["correct_after"] == labels["correct_before"]
        else:
            # a substitution can move the score either way; it may not leave it unexplained
            assert (
                labels["correct_after"] != labels["correct_before"]
                or labels["labels_differing"] == 0
            )

    def test_no_decisions_are_currently_recorded(self) -> None:
        """The shipped state, stated plainly so a regression is loud rather than quiet."""
        labels = json.loads((ROOT / "docs" / "results" / "calibration-labels.json").read_text())
        assert labels["labels_applied"] == 0
        assert (labels["correct_before"], labels["correct_after"]) == (569, 569)

    def test_the_cost_row(self) -> None:
        table = json.loads((ROOT / "docs" / "eval" / "calibration_accuracy.json").read_text())
        cost = table["cost"]
        assert cost["call_count"] == 1701
        assert cost["cost_usd"] == 0.854442
        assert cost["prompt_tokens"] == 5440750
        assert cost["completion_tokens"] == 63882

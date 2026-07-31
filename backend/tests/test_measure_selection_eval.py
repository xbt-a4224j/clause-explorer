"""The offline eval harness itself (#27).

Grading needs no database, no LLM call, no network — the agent's output is a JSON selection
already recorded to disk. `TestRunsFullyOffline` proves that literally, by making any socket
construction raise during the run.

Runs with `OPENAI_API_KEY` unset, and is not marked `needs_key` — it belongs in the ordinary CI
gate precisely because it never calls out.
"""

from __future__ import annotations

import socket

import pytest
from explorer.evals import measure_selection


class TestRunsFullyOffline:
    def test_no_socket_is_ever_constructed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def refuse(*args: object, **kwargs: object) -> None:
            raise AssertionError("measure_selection.run() constructed a socket — not offline")

        monkeypatch.setattr(socket, "socket", refuse)
        summary = measure_selection.run()
        assert summary["case_count"] == 25


class TestTheEvalSetShape:
    def test_25_cases_are_authored(self) -> None:
        summary = measure_selection.run()
        assert summary["case_count"] == 25

    def test_at_least_three_cases_expect_a_refusal(self) -> None:
        summary = measure_selection.run()
        assert summary["refusal_count"] >= 3

    def test_every_case_has_a_recorded_output(self) -> None:
        summary = measure_selection.run()
        assert all(r.error is None for r in summary["results"])


class TestPerCaseResultsAreVisible:
    """An aggregate alone hides a single bad case; the harness must expose each one."""

    def test_results_are_reported_per_case_not_only_aggregated(self) -> None:
        summary = measure_selection.run()
        assert len(summary["results"]) == summary["case_count"]
        assert all(r.id and r.question for r in summary["results"])


class TestScoringSeparatesAnswerableFromRefusal:
    def test_a_refusal_case_carries_no_precision_recall_score(self) -> None:
        summary = measure_selection.run()
        refusals = [r for r in summary["results"] if r.should_refuse]
        assert refusals
        assert all(r.measure_precision is None for r in refusals)

    def test_an_answerable_case_carries_a_measure_score(self) -> None:
        summary = measure_selection.run()
        answerable = [r for r in summary["results"] if not r.should_refuse]
        assert answerable
        assert all(r.measure_precision is not None for r in answerable)

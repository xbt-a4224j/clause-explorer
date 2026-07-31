"""Offline grading harness for `docs/eval/measure_selection.json` (#27).

This is eval #3, and the reason the semantic layer earns its place: the agent's output is a
JSON selection, not prose, so grading it needs no database, no LLM call, and no network. It
reads two committed files — the 25 authored question/expected-selection pairs and the real
recorded model output for each — and produces per-case and aggregate scores in-process.

Answerable and refusal cases are scored separately rather than folded into one number.
Precision/recall on a case where the correct answer is "select nothing" behaves oddly inside
the same formula as an ordinary case, and conflating them would hide exactly the failure mode
this eval exists to catch — a model that answers when it should have declined.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EVAL_SET = ROOT / "docs" / "eval" / "measure_selection.json"
RECORDED = ROOT / "docs" / "eval" / "recorded_outputs.json"


@dataclass(frozen=True)
class CaseResult:
    id: str
    question: str
    should_refuse: bool
    output_refused: bool
    measure_precision: float | None
    measure_recall: float | None
    dimension_precision: float | None
    dimension_recall: float | None
    filters_exact_match: bool | None
    error: str | None = None


def _prf(expected: set[str], actual: set[str]) -> tuple[float, float]:
    if not expected and not actual:
        return 1.0, 1.0
    if not actual:
        return 0.0, 0.0
    if not expected:
        return 0.0, 0.0
    precision = len(expected & actual) / len(actual)
    recall = len(expected & actual) / len(expected)
    return precision, recall


def _normalize_filters(
    filters: list[dict[str, Any]],
) -> frozenset[tuple[str, str, tuple[str, ...]]]:
    return frozenset(
        (f["member"], f["operator"], tuple(sorted(f.get("values", [])))) for f in filters
    )


def grade_case(case: dict[str, Any], recorded: dict[str, Any]) -> CaseResult:
    output = recorded.get("output", {})
    if "error" in output:
        return CaseResult(
            id=case["id"],
            question=case["question"],
            should_refuse=case["should_refuse"],
            output_refused=True,
            measure_precision=None,
            measure_recall=None,
            dimension_precision=None,
            dimension_recall=None,
            filters_exact_match=None,
            error=output["error"],
        )

    output_measures = set(output.get("measures", []))
    output_refused = len(output_measures) == 0

    if case["should_refuse"]:
        return CaseResult(
            id=case["id"],
            question=case["question"],
            should_refuse=True,
            output_refused=output_refused,
            measure_precision=None,
            measure_recall=None,
            dimension_precision=None,
            dimension_recall=None,
            filters_exact_match=None,
        )

    m_p, m_r = _prf(set(case["expected_measures"]), output_measures)
    d_p, d_r = _prf(set(case["expected_dimensions"]), set(output.get("dimensions", [])))
    filters_match = _normalize_filters(case["expected_filters"]) == _normalize_filters(
        output.get("filters", [])
    )

    return CaseResult(
        id=case["id"],
        question=case["question"],
        should_refuse=False,
        output_refused=output_refused,
        measure_precision=m_p,
        measure_recall=m_r,
        dimension_precision=d_p,
        dimension_recall=d_r,
        filters_exact_match=filters_match,
    )


def run(eval_set_path: Path = EVAL_SET, recorded_path: Path = RECORDED) -> dict[str, Any]:
    """Pure and offline: both inputs are files already on disk. Callers assert no network was
    used by wrapping this in a socket-blocking context — see the pytest harness."""
    cases = json.loads(eval_set_path.read_text())
    recorded_by_id = {r["id"]: r for r in json.loads(recorded_path.read_text())}

    results = [grade_case(case, recorded_by_id[case["id"]]) for case in cases]

    answerable = [r for r in results if not r.should_refuse and r.error is None]
    refusal = [r for r in results if r.should_refuse]

    def _mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    return {
        "case_count": len(results),
        "answerable_count": len(answerable),
        "refusal_count": len(refusal),
        "measure_precision": _mean([r.measure_precision for r in answerable]),  # type: ignore[misc]
        "measure_recall": _mean([r.measure_recall for r in answerable]),  # type: ignore[misc]
        "dimension_precision": _mean([r.dimension_precision for r in answerable]),  # type: ignore[misc]
        "dimension_recall": _mean([r.dimension_recall for r in answerable]),  # type: ignore[misc]
        "filter_exact_match_rate": _mean(
            [1.0 if r.filters_exact_match else 0.0 for r in answerable]
        ),
        "refusal_accuracy": _mean(
            [1.0 if r.output_refused == r.should_refuse else 0.0 for r in refusal]
        ),
        "results": results,
    }


if __name__ == "__main__":
    summary = run()
    for r in summary["results"]:
        print(r)
    print({k: v for k, v in summary.items() if k != "results"})

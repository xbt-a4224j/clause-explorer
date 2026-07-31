"""`GET /agent/grading` (#36) — the offline grade over recorded model output.

This endpoint is the semantic-layer argument reduced to a number a reviewer can check. Because
the model emits a *selection* from a fixed vocabulary rather than freeform SQL, correctness is
a discrete question — did it pick the right measure and filters — and can be scored with **no
database and no model**. Both inputs are committed fixtures; a test forbids `psycopg.connect`
for the duration of the call to keep that honest.

Refusal cases are reported separately rather than averaged in. Refusal accuracy is the worst
number in this eval, and folding it into a headline would bury the finding a sceptical reader
should hear first: the model is bad at knowing when to decline, which is exactly why `min_n` is
enforced in FastAPI and not in a prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from explorer.api.logging import get_logger

router = APIRouter(prefix="/agent")
log = get_logger()

ROOT = Path(__file__).resolve().parents[3]
CASES_FILE = ROOT / "docs" / "eval" / "measure_selection.json"
RECORDED_FILE = ROOT / "docs" / "eval" / "recorded_outputs.json"


class GradedCase(BaseModel):
    id: str
    question: str
    should_refuse: bool
    expected_measures: list[str]
    actual_measures: list[str]
    expected_dimensions: list[str]
    actual_dimensions: list[str]
    correct: bool


class GradingResponse(BaseModel):
    cases: list[GradedCase]
    answerable_total: int
    answerable_correct: int
    refusal_total: int
    refusal_correct: int
    #: the size of the vocabulary a selection is graded against, from the recorded run
    note: str


def _load(path: Path) -> Any:
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                f"{path.name} is not committed. Run "
                "`PYTHONPATH=backend python -m explorer.evals.record_measure_selection` "
                "(needs a key) and commit the result."
            ),
        )
    return json.loads(path.read_text())


@router.get("/grading", response_model=GradingResponse)
def grading() -> GradingResponse:
    cases = _load(CASES_FILE)
    recorded = {r["id"]: r.get("output") or {} for r in _load(RECORDED_FILE)}

    graded: list[GradedCase] = []
    for case in cases:
        out = recorded.get(case["id"], {})
        actual_m = list(out.get("measures") or [])
        actual_d = list(out.get("dimensions") or [])
        if case["should_refuse"]:
            # A refusal is correct only when the model selected nothing at all. Selecting a
            # plausible measure for an unanswerable question is the failure being measured.
            correct = not actual_m and not actual_d
        else:
            correct = set(actual_m) == set(case["expected_measures"]) and set(actual_d) == set(
                case["expected_dimensions"]
            )
        graded.append(
            GradedCase(
                id=case["id"],
                question=case["question"],
                should_refuse=case["should_refuse"],
                expected_measures=case["expected_measures"],
                actual_measures=actual_m,
                expected_dimensions=case["expected_dimensions"],
                actual_dimensions=actual_d,
                correct=correct,
            )
        )

    answerable = [g for g in graded if not g.should_refuse]
    refusals = [g for g in graded if g.should_refuse]
    log.info("grading_read", cases=len(graded))
    return GradingResponse(
        cases=graded,
        answerable_total=len(answerable),
        answerable_correct=sum(1 for g in answerable if g.correct),
        refusal_total=len(refusals),
        refusal_correct=sum(1 for g in refusals if g.correct),
        note=(
            "Graded from committed fixtures with no database and no model call. Exact-set "
            "match on measures and dimensions — stricter than the precision/recall figures in "
            "docs/results/measure-selection.md, which give partial credit."
        ),
    )

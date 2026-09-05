"""`POST /agent/selection-correction` (#51) — a confirmed selection, recorded as eval data.

When someone edits a chip on Ask before running, that is a **labelled disagreement**: here is
what the model selected, here is what a person said it should have selected. The
measure-selection eval has 25 authored cases written in July against a vocabulary someone was
probing on purpose; every real correction is a case it does not have.

Agreements are written too. An eval fed only corrections learns only what the model got wrong,
and "it was right and nobody touched it" is the other half of any accuracy figure. Recording
only the disagreements would produce a corrections accuracy of 0.00 by construction.

**Only a human writes here.** This route is reached from the confirm click on Ask and from
nowhere else. `/agent/ask` never writes to the table, and a test asserts it. A model recording
its own eval data would be storing an opinion it already held rather than evidence against it,
which is the difference between an eval and a mirror.

The two selections are stored as JSONB rather than shredded into columns. The shape is Cube's
query object, already versioned by `cube/model/*.yml`; a normalized selection schema here
would be a second definition of what a selection is, and the one that goes stale.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from explorer.api.logging import get_logger
from explorer.api.settings import settings

router = APIRouter(prefix="/agent")
log = get_logger()

#: The parts of a selection a person can disagree with, named individually. One boolean
#: "changed" flag would record that someone edited something without recording what, and
#: which part people correct is the finding — the model is measured far weaker on the filter
#: value (0.50 exact-match) than on the measure (0.80 precision).
SELECTION_FIELDS = ("measures", "dimensions", "filters")


def _normalize(value: Any) -> Any:
    """A selection is a set of names, so ordering is not a disagreement. Counting a reordered
    list as a correction would inflate the rate with noise the model did not cause."""
    if isinstance(value, list):
        return sorted(json.dumps(_normalize(v), sort_keys=True) for v in value)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in sorted(value.items())}
    return value


def changed_fields(model_selection: dict[str, Any], confirmed: dict[str, Any]) -> list[str]:
    """Which parts of the selection the person changed, in a stable order."""
    return [
        field
        for field in SELECTION_FIELDS
        if _normalize(model_selection.get(field, [])) != _normalize(confirmed.get(field, []))
    ]


class CorrectionRequest(BaseModel):
    # module scope: `from __future__ import annotations` plus a model defined in a function
    # raises PydanticUndefinedAnnotation (CLAUDE.md, known traps)
    model_config = ConfigDict(protected_namespaces=())

    question: str = Field(min_length=1, max_length=1000)
    model_selection: dict[str, Any]
    confirmed_selection: dict[str, Any]
    #: who confirmed it. Defaults to the single local reviewer this app has, and lets a test
    #: delete only its own rows rather than truncating a table holding real decisions.
    labeller: str = "local"


class CorrectionResponse(BaseModel):
    id: int
    agreed: bool
    changed_fields: list[str]


@router.post("/selection-correction", response_model=CorrectionResponse)
def record_correction(request: CorrectionRequest) -> CorrectionResponse:
    changed = changed_fields(request.model_selection, request.confirmed_selection)
    agreed = not changed

    try:
        with psycopg.connect(settings.database_url) as conn:
            row = conn.execute(
                "INSERT INTO selection_corrections "
                "(question, model_selection, confirmed_selection, changed_fields, agreed, "
                " labeller) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    request.question,
                    json.dumps(request.model_selection),
                    json.dumps(request.confirmed_selection),
                    changed,
                    agreed,
                    request.labeller,
                ),
            ).fetchone()
            conn.commit()
    except psycopg.Error as exc:
        # Named rather than swallowed: a correction silently dropped is eval data lost, and
        # the user has no way to tell it did not land.
        log.warning("selection_correction_failed", error=type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail=(
                "The correction could not be recorded. Run "
                "`PYTHONPATH=backend python -m explorer.db.migrate up` if "
                "selection_corrections is not migrated yet."
            ),
        ) from exc

    correction_id = int(row[0]) if row else 0
    log.info(
        "selection_correction",
        id=correction_id,
        agreed=agreed,
        changed_fields=changed,
    )
    return CorrectionResponse(id=correction_id, agreed=agreed, changed_fields=changed)


class CorrectionsGrade(BaseModel):
    """The corrections half of the grade (#51), served apart from the authored set.

    Not on `/agent/grading` on purpose. That endpoint's stated property — and a test pins it by
    forbidding `psycopg.connect` for the duration of the call — is that it grades with no
    database and no model. These rows live in Postgres. Putting them there would have cost the
    authored grade the one property that makes it checkable by a reader with nothing running.
    """

    corrections_count: int
    corrections_agreed: int
    #: None when nothing has been recorded — n=0, not "the model is always wrong"
    corrections_accuracy: float | None
    #: which part of a selection people actually correct, e.g. {"filters": 3}
    changed_field_counts: dict[str, int]
    note: str


@router.get("/corrections-grade", response_model=CorrectionsGrade)
def corrections_grade() -> CorrectionsGrade:
    from explorer.evals.measure_selection import grade_corrections

    summary = grade_corrections(load_corrections())
    log.info("corrections_grade_read", count=summary["corrections_count"])
    return CorrectionsGrade(
        corrections_count=summary["corrections_count"],
        corrections_agreed=summary["corrections_agreed"],
        corrections_accuracy=summary["corrections_accuracy"],
        changed_field_counts=summary["changed_field_counts"],
        note=(
            "Real confirmations recorded on Ask. Reported apart from the 25 authored cases "
            "and never averaged with them: the authored set was written to probe the "
            "vocabulary and deliberately includes five questions that should be refused, "
            "while this is whatever people happened to ask."
        ),
    )


def load_corrections(limit: int = 500) -> list[dict[str, Any]]:
    """The recorded rows, for the grading panel. Returns `[]` when the table is not migrated:
    a grading endpoint must still answer for the authored set, which needs no database at all.
    """
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            rows = conn.execute(
                "SELECT question, changed_fields, agreed, created_at "
                "FROM selection_corrections ORDER BY id DESC LIMIT %s",
                (limit,),
            ).fetchall()
    except psycopg.Error:
        return []
    return [
        {
            "question": r[0],
            "changed_fields": list(r[1] or []),
            "agreed": bool(r[2]),
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]

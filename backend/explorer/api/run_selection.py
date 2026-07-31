"""`POST /agent/run-selection` (#37) — execute a selection the user assembled by clicking.

The Semantic Layer builder offers no free-text input, so a client cannot *type* an invalid
measure name. That is a property of one UI, not a guarantee about the system, and this endpoint
is where the guarantee lives: every name is checked against Cube's live catalog **before**
anything reaches Cube.

Ordering matters more than it looks. Validating after the query has run would still return a
422 to the caller while having already executed whatever was asked for — so the check is first,
and a test asserts Cube was never touched on the reject path.

`min_n` applies here exactly as it does on the dashboard path. The gate does not care how a
query was assembled: a thin slice is a thin slice whether a partner filtered into it, an agent
selected into it, or someone built it by hand in this panel. Anything else would make the
builder a documented bypass.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.agent.select import (
    AgentUnavailable,
    InvalidSelection,
    fetch_vocabulary,
    validate_selection,
)
from explorer.api.cube_client import CubeUnavailable
from explorer.api.cube_client import query as cube_query
from explorer.api.logging import get_logger
from explorer.api.settings import settings

router = APIRouter(prefix="/agent")
log = get_logger()

#: the measure whose value is the denominator on every deal-point rollup
COUNT_MEASURE = "deal_points.n"


class Filter(BaseModel):
    member: str
    operator: str = "equals"
    values: list[str] = Field(default_factory=list)


class RunSelectionRequest(BaseModel):
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=1000)


class RunSelectionResponse(BaseModel):
    #: echoed verbatim so the builder's JSON pane cannot show one query and run another
    query: dict[str, Any]
    rows: list[dict[str, Any]]
    #: the denominator, when the selection carries one
    n: int | None = None
    refused: bool = False
    threshold: int | None = None
    message: str | None = None


def _n_from(rows: list[dict[str, Any]]) -> int | None:
    """The count measure, if it was selected. Absent when the user picked only a median — in
    which case there is no denominator to gate on and none is claimed."""
    if not rows:
        return None
    value = rows[0].get(COUNT_MEASURE)
    return int(value) if value is not None else None


@router.post("/run-selection", response_model=RunSelectionResponse)
def run_selection(request: RunSelectionRequest) -> RunSelectionResponse:
    selection: dict[str, Any] = {
        "measures": request.measures,
        "dimensions": request.dimensions,
        "filters": [f.model_dump() for f in request.filters],
    }

    try:
        vocabulary = fetch_vocabulary()
    except AgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # FIRST. Nothing below this line runs on an invalid name.
    try:
        validate_selection(selection, vocabulary)
    except InvalidSelection as invalid:
        log.warning("run_selection_rejected", reason=str(invalid))
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid

    payload = {**selection, "limit": request.limit}
    try:
        rows = cube_query(payload)
    except CubeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    n = _n_from(rows)
    if n is not None and n < settings.min_n:
        # Refusal is its own shape, never an empty row list with a 200 — "we will not answer
        # this" and "there is nothing here" are different statements about different things.
        log.info("run_selection_refused", n=n, threshold=settings.min_n)
        return RunSelectionResponse(
            query=payload,
            rows=[],
            n=n,
            refused=True,
            threshold=settings.min_n,
            message=(
                f"n={n} — insufficient to characterize (threshold {settings.min_n}). "
                "The same gate applies to the dashboard and to a direct API call."
            ),
        )

    log.info("run_selection", measures=request.measures, row_count=len(rows), n=n)
    return RunSelectionResponse(query=payload, rows=rows, n=n, refused=False)

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

from explorer.agent.dimension_values import dimension_values
from explorer.agent.pick_value import pick_value
from explorer.agent.resolve_filter_value import UnresolvedFilterValue, resolve_against
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
# Every count measure in the vocabulary, widest-grain first. Both namespaces call theirs `n`,
# so a single hardcoded key silently disabled the gate on whichever one it was not — which is
# how a slice of one came back carrying target and acquirer names with `refused: false`.
COUNT_MEASURES = (
    "comparable_deals.n",  # one row per agreement
    "deal_points.count_distinct_matters",  # agreements, counted explicitly
    "deal_points.n",  # one row per ANSWER: over-counts agreements ~89x
)


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
    #: cells dropped for being below `min_n`. Declared rather than silent: a reader who
    #: believes they are seeing the whole distribution will find the denominators do not add
    #: up, which is a worse failure than being told a cell was withheld.
    suppressed: int = 0


def _row_clears(row: dict[str, Any], threshold: int) -> bool:
    """Whether one cell is big enough to be characterized. A row carrying no count at all
    clears: there is no denominator to gate on, and inventing one to suppress by would be a
    claim about a sample size nobody measured."""
    n = _n_from([row])
    return n is None or n >= threshold


def _n_from(rows: list[dict[str, Any]]) -> int | None:
    """The smallest agreement count anywhere in the result, or None if none was selected.

    SMALLEST, on two axes, because both were holes:

    * across ROWS — a grouped result is a set of cells and the gate protects each one.
      Reading `rows[0]` served a fourth cell of n=3 behind a first cell of 89, a cell that
      refuses instantly when requested on its own.
    * across MEASURES — `deal_points.n` counts answers, not agreements: healthcare is 26
      agreements but 2,245 answers. Taking the minimum prefers whichever selected measure is
      closest to an agreement count, so the gate cannot be walked past by selecting the
      inflated one.

    None when no count was selected at all (a median on its own), where there is no
    denominator to gate on and none is claimed.
    """
    counts = [int(row[m]) for row in rows for m in COUNT_MEASURES if row.get(m) is not None]
    return min(counts) if counts else None


def resolve_filters(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace every filter value with one the corpus actually carries, or refuse loudly.

    This endpoint is reachable by curl and by the click-builder, not only by the model, and the
    UI describes it as "the same path". It was not: /agent/ask resolved values and this did
    not, so 'Healthcare', 'cash' and 'no-shop' arrived at Cube verbatim and came back n=0 —
    indistinguishable from a genuinely empty slice.

    A dimension with no closed vocabulary (a target name, a date) travels verbatim. Refusing
    those would make the resolver a censor rather than a translator.
    """
    resolved: list[dict[str, Any]] = []
    for f in filters:
        member = f["member"]
        candidates = dimension_values(member)
        if not candidates:
            resolved.append(f)
            continue
        values: list[str] = []
        for raw in f.get("values") or []:
            try:
                values.append(resolve_against(raw, candidates, pick=pick_value).resolved)
            except UnresolvedFilterValue as unresolved:
                raise InvalidSelection(
                    f"{raw!r} is not a value {member} carries. Filtering on it would return "
                    f'zero rows, which reads as "we have no comparable deals" rather than '
                    f'"that value does not exist". Near misses: '
                    f"{', '.join(repr(c) for c in unresolved.candidates[:5])}.",
                    {"filters": filters},
                ) from unresolved
        resolved.append({**f, "values": values})
    return resolved


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

    # Values, after names. Names are enum-locked at decode time; values are free text and are
    # the half that silently returned zero rows until now.
    try:
        selection["filters"] = resolve_filters(selection["filters"])
    except InvalidSelection as invalid:
        log.warning("run_selection_unresolved", reason=str(invalid))
        raise HTTPException(status_code=422, detail=str(invalid)) from invalid

    payload = {**selection, "limit": request.limit}
    try:
        rows = cube_query(payload)
    except CubeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Per-CELL suppression, before the whole-result gate. A grouped result is a set of
    # independent claims and each is gated on its own: refusing all four cells of a
    # consideration split because the fourth is n=3 answers nothing, and published deal-point
    # studies do exactly this — report the categories with enough sample, say the rest were
    # too thin. The cost, accepted knowingly: a reader can infer a suppressed cell exists and
    # is small. Every disclosure-control system makes that trade.
    suppressed = 0
    if request.dimensions:
        kept = [r for r in rows if _row_clears(r, settings.min_n)]
        suppressed = len(rows) - len(kept)
        if suppressed and kept:
            log.info("run_selection_suppressed", suppressed=suppressed, kept=len(kept))
            return RunSelectionResponse(
                query=payload,
                rows=kept,
                n=_n_from(kept),
                refused=False,
                threshold=settings.min_n,
                suppressed=suppressed,
                message=(
                    f"{suppressed} of {len(rows)} rows suppressed: below the threshold of "
                    f"{settings.min_n}. The remaining rows are unchanged; the distribution "
                    "shown is therefore incomplete."
                ),
            )
        rows = kept or rows

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

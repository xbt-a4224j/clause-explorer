"""`POST /deal-terms` — what was negotiated across a selected set (#21).

This is the view that replaces a comparison chart an associate builds by hand from eight
agreements, and the discipline it has to hold is reporting discipline rather than arithmetic:

**"6 of 8", never "75%".** Below `settings.percentage_threshold` a prevalence renders as a
count. A percentage implies a precision the sample does not support, and this is the figure a
partner quotes in a pitch. The threshold is config so the rendering rule can be tested at its
exact edge rather than asserted in prose.

**Absence is a finding.** A deal point that nobody in the set negotiated is a row reading
`0 of 8`, not an omission. "We checked and it is not there" and "we did not check" look
identical once the row is gone, and only one of them is useful.

**Every figure carries the denominator it was computed against.** `answered_n` is the number of
selected matters with a labelled answer for that deal point — which is not the size of the
selection, because MAUD does not answer every deal point for every agreement.

Numbers come from Cube, never from SQL written here: the facet count, the rollup and the
coverage grid have to mean the same thing, and that only holds if there is one definition.
"""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.api.cube_client import CubeUnavailable
from explorer.api.cube_client import query as cube_query
from explorer.api.logging import get_logger
from explorer.api.matters import slice_source
from explorer.api.settings import settings

router = APIRouter()
log = get_logger()

NAME = "deal_points.deal_point_name"
MATTER_ID = "deal_points.matter_id"
POSITION = "deal_points.position"
N = "deal_points.n"
PRESENT = "deal_points.present_count"
NUMERIC_N = "deal_points.numeric_n"
MEDIAN = "deal_points.median_numeric_value"
P25 = "deal_points.p25_numeric_value"
P75 = "deal_points.p75_numeric_value"

# Stated on the response rather than left to UI copy, so it travels with the numbers into any
# client that renders them — including a pasted paragraph.
SCOPE_NOTE = (
    "These are comparable PUBLIC deals from the MAUD study of SEC-filed merger agreements. "
    "This is not this firm's own matter history and must not be described as it."
)


class DealTermsRequest(BaseModel):
    matter_ids: list[str] = Field(
        min_length=1,
        description="The selected set from Explore. Required: an unfiltered rollup would "
        "silently answer about the whole corpus.",
    )


class DrillRequest(BaseModel):
    matter_ids: list[str] = Field(min_length=1)
    deal_point_name: str


class NumericSummary(BaseModel):
    numeric_n: int
    median: float | None
    p25: float | None
    p75: float | None


class PositionCount(BaseModel):
    position: str
    n: int


class DealTermRow(BaseModel):
    deal_point_name: str
    answered_n: int = Field(
        description="Selected matters with a labelled answer for this deal point. The "
        "denominator — not the size of the selection."
    )
    present_count: int = Field(
        description="Of the answered set, how many record the provision as present."
    )
    display: str = Field(description='Pre-rendered per the threshold rule: "6 of 8" or "62%".')
    display_kind: str = Field(description='"count" below the threshold, "percentage" at or above.')
    positions: list[PositionCount]
    numeric: NumericSummary | None


class DealTermsResponse(BaseModel):
    selection_n: int
    percentage_threshold: int
    rows: list[DealTermRow]
    answered_deal_point_count: int
    absent_deal_point_count: int
    scope_note: str = SCOPE_NOTE


class DrillMatter(BaseModel):
    matter_id: str
    target_name: str | None
    position: str
    source_file: str | None
    source_span_start: int | None
    source_span_end: int | None
    clause_text: str | None = Field(
        default=None,
        description="The exact characters at [start, end) in the source agreement.",
    )
    text_unavailable: str | None = Field(
        default=None, description="Why there is no clause text. Set whenever clause_text is null."
    )


class DrillResponse(BaseModel):
    deal_point_name: str
    matters: list[DrillMatter]
    scope_note: str = SCOPE_NOTE


def _selection_filter(matter_ids: list[str]) -> list[dict[str, Any]]:
    return [{"member": MATTER_ID, "operator": "equals", "values": matter_ids}]


def render(present: int, answered: int, selection_n: int, threshold: int) -> tuple[str, str]:
    """The count-vs-percentage rule, in one place so it cannot drift between callers.

    `answered` is the denominator when there is one. When no selected matter has an answer at
    all, the honest denominator is the selection itself: "0 of 8" says we looked at eight
    agreements and none of them speaks to this point.
    """
    if answered == 0:
        return f"0 of {selection_n}", "count"
    if answered < threshold:
        return f"{present} of {answered}", "count"
    return f"{round(100 * present / answered)}%", "percentage"


def _positions(matter_ids: list[str], names: set[str]) -> dict[str, list[PositionCount]]:
    """The distribution of answers per deal point.

    MAUD records absence as the literal answer "None" for most deal points but not all, so a
    deal point whose answers are graded standards rather than present/absent is only readable
    through this distribution — `present_count` alone would mislead on it.
    """
    rows = cube_query(
        {
            "measures": [N],
            "dimensions": [NAME, POSITION],
            "filters": _selection_filter(matter_ids),
            "order": {N: "desc"},
        }
    )
    out: dict[str, list[PositionCount]] = {}
    for row in rows:
        name = row.get(NAME)
        if name not in names:
            continue
        out.setdefault(str(name), []).append(
            PositionCount(position=str(row.get(POSITION)), n=int(row[N]))
        )
    return out


def _vocabulary() -> list[str]:
    """Every deal point the corpus knows about, so absence can be reported.

    Read from the data rather than hardcoded: a 93rd deal point is then just rows (D8), and it
    appears here the day it lands with no code change.
    """
    rows = cube_query({"dimensions": [NAME]})
    return [str(r[NAME]) for r in rows if r.get(NAME)]


@router.post("/deal-terms", response_model=DealTermsResponse)
def deal_terms(request: DealTermsRequest) -> DealTermsResponse:
    matter_ids = request.matter_ids
    threshold = settings.percentage_threshold

    try:
        rollup = cube_query(
            {
                "measures": [PRESENT, N, NUMERIC_N, MEDIAN, P25, P75],
                "dimensions": [NAME],
                "filters": _selection_filter(matter_ids),
                "order": {PRESENT: "desc"},
            }
        )
        answered_names = {str(r[NAME]) for r in rollup if r.get(NAME)}
        positions = _positions(matter_ids, answered_names)
        vocabulary = _vocabulary()
    except CubeUnavailable as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    selection_n = len(set(matter_ids))
    rows: list[DealTermRow] = []

    for row in rollup:
        name = str(row[NAME])
        answered = int(row.get(N) or 0)
        present = int(row.get(PRESENT) or 0)
        display, kind = render(present, answered, selection_n, threshold)

        numeric_n = int(row.get(NUMERIC_N) or 0)
        numeric = (
            NumericSummary(
                numeric_n=numeric_n,
                median=_as_float(row.get(MEDIAN)),
                p25=_as_float(row.get(P25)),
                p75=_as_float(row.get(P75)),
            )
            if numeric_n
            else None
        )

        rows.append(
            DealTermRow(
                deal_point_name=name,
                answered_n=answered,
                present_count=present,
                display=display,
                display_kind=kind,
                positions=positions.get(name, []),
                numeric=numeric,
            )
        )

    # Absence is a finding: a deal point the selection never answers is a visible 0-row.
    absent = [name for name in vocabulary if name not in answered_names]
    for name in sorted(absent):
        display, kind = render(0, 0, selection_n, threshold)
        rows.append(
            DealTermRow(
                deal_point_name=name,
                answered_n=0,
                present_count=0,
                display=display,
                display_kind=kind,
                positions=[],
                numeric=None,
            )
        )

    log.info(
        "deal_terms_rollup",
        selection_n=selection_n,
        answered_deal_points=len(answered_names),
        absent_deal_points=len(absent),
        threshold=threshold,
    )

    return DealTermsResponse(
        selection_n=selection_n,
        percentage_threshold=threshold,
        rows=rows,
        answered_deal_point_count=len(answered_names),
        absent_deal_point_count=len(absent),
    )


@router.post("/deal-terms/drill", response_model=DrillResponse)
def drill(request: DrillRequest) -> DrillResponse:
    """Which selected matters answer this deal point, how, and **the clause language itself**.

    Returning the matter id and the position alone is a list of pointers, not a drill-through:
    the associate this view exists to replace would still have to open eight agreements. So the
    text comes back with the source file and the character range it was taken from.

    This reads Postgres rather than Cube deliberately. Cube's footprint is facet counts, the
    rollup and the coverage grid; fetching individual records and their source spans is outside
    it, and going through Cube for row-level text would put document text in the aggregate layer.
    """
    with psycopg.connect(settings.database_url) as conn:
        rows = conn.execute(
            """
            SELECT dp.matter_id, m.target_name, dp.position,
                   m.source_file, dp.source_span_start, dp.source_span_end
              FROM deal_points dp
              JOIN matters m ON m.id = dp.matter_id
             WHERE dp.deal_point_name = %(name)s
               AND dp.matter_id = ANY(%(ids)s)
             ORDER BY dp.matter_id
            """,
            {"name": request.deal_point_name, "ids": list(request.matter_ids)},
        ).fetchall()

    matters: list[DrillMatter] = []
    for matter_id, target_name, position, source_file, start, end in rows:
        clause_text, unavailable = slice_source(source_file, start, end)
        matters.append(
            DrillMatter(
                matter_id=matter_id,
                target_name=target_name,
                position=position,
                source_file=source_file,
                source_span_start=start,
                source_span_end=end,
                clause_text=clause_text,
                text_unavailable=unavailable,
            )
        )

    log.info(
        "deal_terms_drill",
        deal_point_name=request.deal_point_name,
        matters=len(matters),
        located=sum(1 for m in matters if m.clause_text),
    )
    return DrillResponse(deal_point_name=request.deal_point_name, matters=matters)


def _as_float(value: Any) -> float | None:
    return None if value is None else float(value)

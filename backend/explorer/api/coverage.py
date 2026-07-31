"""`POST /coverage` — where the corpus is thick or thin (#22).

The design inversion is the point: default BI styling emphasises the big numbers, but for a KM
team a gap is more actionable than a strength they already know about. So this endpoint makes
thinness *explicit data* rather than something the view infers — every cell states whether it is
reportable and, when it is not, why. A client cannot accidentally render a thin cell as an
ordinary one, and the grid agrees with the Deal Terms refusal (#23) by construction because both
read the same `min_n`.

**Empty cells are returned, not omitted.** A missing row and a zero are the same picture once
the cell is gone, and only one of them is a finding.

The column axis is `signing_year` by default. #22 specifies deal size, and `deal_value_usd` is
NULL on all 152 matters (#9), so that grid is exactly one column wide. Deal size is still
offered — it is not silently substituted — and both axes carry a note saying what they are.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.api.cube_client import CubeUnavailable
from explorer.api.cube_client import query as cube_query
from explorer.api.logging import get_logger
from explorer.api.settings import settings

router = APIRouter()
log = get_logger()

LABEL = "comparable_deals.label"
CODE = "comparable_deals.code"
YEAR = "comparable_deals.signing_year"
BAND = "comparable_deals.deal_size_band"
N = "comparable_deals.n"

COLUMN_DIMENSION = {"year": YEAR, "band": BAND}

COLUMN_NOTE = {
    "year": (
        "Columns are signing year. Deal size is the intended axis (#22) but deal_value_usd is "
        "NULL on all 152 matters, so that grid would be one column wide — see issue #9."
    ),
    "band": (
        "Columns are deal size, which currently has a single value: no deal values have been "
        "enriched yet (#9). The axis is shown as requested, not as a finding about the market."
    ),
}

INSUFFICIENT = "insufficient to characterize"


class CoverageRequest(BaseModel):
    column: Literal["year", "band"] = Field(
        default="year", description="Which axis forms the columns."
    )


class Cell(BaseModel):
    column: str
    n: int
    reportable: bool = Field(
        description="False when n is below min_n. The Deal Terms rollup will refuse on it."
    )
    note: str | None = Field(
        default=None, description="Why the cell is not reportable. None when it is."
    )
    folio_industry_code: str | None = Field(
        default=None,
        description="What Explore filters by when this cell is clicked — the "
        "code, never the display label (#25).",
    )


class Row(BaseModel):
    label: str
    folio_industry_code: str | None
    cells: list[Cell]
    total_n: int


class CoverageResponse(BaseModel):
    rows: list[Row]
    columns: list[str]
    column_axis: str
    column_note: str
    column_totals: dict[str, int]
    total_n: int
    min_n: int
    thin_cell_count: int
    empty_cell_count: int


@router.post("/coverage", response_model=CoverageResponse)
def coverage(request: CoverageRequest) -> CoverageResponse:
    dimension = COLUMN_DIMENSION[request.column]
    min_n = settings.min_n

    try:
        rows = cube_query(
            {
                "measures": [N],
                "dimensions": [LABEL, CODE, dimension],
                "order": {N: "desc"},
            }
        )
    except CubeUnavailable as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    # Build the full cartesian grid: every industry gets a cell in every column, present in the
    # data or not. Omitting the misses is what turns a gap into an invisible one.
    counts: dict[tuple[str, str], int] = {}
    codes: dict[str, str | None] = {}
    columns: list[str] = []
    labels: list[str] = []

    for row in rows:
        label = str(row[LABEL]) if row.get(LABEL) is not None else "unclassified"
        column = str(row[dimension]) if row.get(dimension) is not None else "unclassified"
        if label not in labels:
            labels.append(label)
            codes[label] = str(row[CODE]) if row.get(CODE) is not None else None
        if column not in columns:
            columns.append(column)
        counts[(label, column)] = counts.get((label, column), 0) + int(row[N])

    columns.sort()

    grid: list[Row] = []
    thin = 0
    empty = 0
    for label in labels:
        cells: list[Cell] = []
        for column in columns:
            n = counts.get((label, column), 0)
            reportable = n >= min_n
            if not reportable:
                thin += 1
            if n == 0:
                empty += 1
            cells.append(
                Cell(
                    column=column,
                    n=n,
                    reportable=reportable,
                    note=None if reportable else f"n={n} — {INSUFFICIENT} (threshold {min_n})",
                    folio_industry_code=codes[label],
                )
            )
        grid.append(
            Row(
                label=label,
                folio_industry_code=codes[label],
                cells=cells,
                total_n=sum(c.n for c in cells),
            )
        )

    column_totals = {
        column: sum(counts.get((label, column), 0) for label in labels) for column in columns
    }

    log.info(
        "coverage_grid",
        column_axis=request.column,
        rows=len(grid),
        columns=len(columns),
        thin_cells=thin,
        empty_cells=empty,
        min_n=min_n,
    )

    return CoverageResponse(
        rows=grid,
        columns=columns,
        column_axis=request.column,
        column_note=COLUMN_NOTE[request.column],
        column_totals=column_totals,
        total_n=sum(r.total_n for r in grid),
        min_n=min_n,
        thin_cell_count=thin,
        empty_cell_count=empty,
    )

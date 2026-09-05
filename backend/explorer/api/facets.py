"""`POST /facets` — live facet counts from Cube for the Explore rail (#19).

Counts are Cube queries, not precomputed and not counted in Python. The point of the semantic
layer is that the number in the facet rail and the number in a deal-terms rollup come from the
same definition; computing facets here with `SELECT count(*)` would quietly create a second
definition that drifts.

**Zero-count values are returned, not dropped.** A facet value that disappears when it hits
zero tells the user nothing; one that renders disabled with `n=0` tells them the corpus has
nothing there, which is a real answer. #48 cut the Coverage tab, so this rail is now the only
place in the product carrying that argument: a gap is a finding, not something to smooth over.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.api.cube_client import CubeUnavailable
from explorer.api.cube_client import query as cube_query

router = APIRouter()

INDUSTRY_DIMENSION = "comparable_deals.label"
# The stable identifier behind the label. /comparables filters by code, so the rail must hand
# one back — resolving a display string to a code later is the failure #25 exists to prevent.
CODE_DIMENSION = "comparable_deals.code"
YEAR_DIMENSION = "comparable_deals.signing_year"
BAND_DIMENSION = "comparable_deals.deal_size_band"
# Deal size is empty (#9); consideration type is the honest substitute — a MAUD
# expert label, populated for all 152, and the axis a partner asks about next.
CONSIDERATION_DIMENSION = "comparable_deals.consideration_type"
COUNT_MEASURE = "comparable_deals.n"
# Corpus totals for the landing state (demo script 1 beat 1)
DEAL_POINT_COUNT = "deal_points.n"


class FacetRequest(BaseModel):
    folio_industry_label: str | None = Field(default=None)
    signing_year: int | None = Field(default=None)
    deal_size_band: str | None = Field(default=None)
    consideration_type: str | None = Field(default=None)


class FacetValue(BaseModel):
    value: str
    n: int
    selected: bool
    reason: str | None = Field(
        default=None,
        description=(
            "Why this bucket exists, for buckets that are an absence rather than a value. "
            "`unclassified` with a bare count reads as a bug; it is a provenance fact, and "
            "which fact differs per dimension (#34)."
        ),
    )
    code: str | None = Field(
        default=None,
        description=(
            "The stable identifier to filter by, where the dimension has one. None for a "
            "bucket with no concept behind it (unclassified) — inventing a code there would "
            "silently return nothing."
        ),
    )


class FacetGroup(BaseModel):
    key: str
    label: str
    values: list[FacetValue]
    total_n: int | None = Field(
        default=None,
        description=(
            "Matters in the current slice that carry ANY value for this dimension. None when "
            "the group is unavailable — advertising a filterable total directly above 'not "
            "filterable' is the header contradicting its own note (#34)."
        ),
    )
    total_basis: str = Field(
        default="",
        description=(
            "What total_n counts, in words. A group total and a value count are different "
            "denominators and were rendered identically; on a product whose central claim is "
            "that every figure carries its denominator, that ambiguity was the worst one (#34)."
        ),
    )
    inferred: bool = Field(
        default=False,
        description=(
            "True where the dimension's values are classifier output rather than expert "
            "labels. Industry is derived from a self-assigned SIC code through a checked-in "
            "crosswalk; the rail is where someone filters on it and was the one place that "
            "did not say so (#34)."
        ),
    )
    unavailable: str | None = Field(
        default=None,
        description=(
            "Set when the group has no value worth filtering on, with the reason. The group "
            "still renders, disabled — omitting it would claim the corpus has no such axis, "
            "when the axis exists and the data behind it does not."
        ),
    )


# A dimension whose only value is this carries no information: every matter is in one bucket,
# so selecting it filters nothing. Distinct from a value that is genuinely zero.
UNINFORMATIVE = {"unknown", "unclassified"}

# Why an absence bucket exists, per dimension. Server-side and per-key rather than one
# generic string, because the causes are genuinely different: EDGAR resolved no industry for
# some registrants, parsed no signing date for others, and deal value is not populated at all.
VALUE_REASONS = {
    "industry": (
        "No industry: EDGAR did not resolve this matter's registrant to an SIC code, so the "
        "SIC to FOLIO crosswalk had nothing to map. 139 of 152 matters resolved."
    ),
    "year": (
        "No signing year: no signing date was parsed from the filing header for these matters."
    ),
    "band": (
        "No size band: deal value is not populated for any matter, so every one falls in the "
        "same bucket. Issue #9."
    ),
    "consideration": "No consideration type recorded for this matter in MAUD.",
}

#: dimensions whose values are classifier output, not expert labels
INFERRED_GROUPS = {"industry"}

#: what a group's total_n counts, in words — the denominator, stated
TOTAL_BASIS = {
    "industry": "matters in this slice with any industry resolved",
    "year": "matters in this slice with a signing year",
    "band": "matters in this slice with a size band",
    "consideration": "matters in this slice with a consideration type (MAUD expert label)",
}

REASONS = {
    "band": (
        "Deal size is not filterable: no deal values have been enriched yet, so all 152 "
        "matters sit in one bucket. Tracked as issue #9."
    ),
}


class CorpusCounts(BaseModel):
    """What is loaded, visible before any interaction.

    An empty-looking rail could mean a small corpus or a broken ingest; these three numbers
    tell the two apart without opening psql.
    """

    matters: int
    deal_points: int
    industries: int


class FacetsResponse(BaseModel):
    groups: list[FacetGroup]
    total_n: int
    unfiltered_n: int
    corpus: CorpusCounts


def _filters(request: FacetRequest, exclude: str) -> list[dict[str, Any]]:
    """Every active filter except this group's own.

    A facet group must not filter itself, or selecting "Health Care" collapses the industry
    rail to a single value and the user cannot see what else is available or switch. This is
    the standard faceted-search rule and it is easy to get wrong by filtering uniformly.
    """
    active: list[dict[str, Any]] = []
    if request.folio_industry_label and exclude != "industry":
        active.append(
            {
                "member": INDUSTRY_DIMENSION,
                "operator": "equals",
                "values": [request.folio_industry_label],
            }
        )
    if request.signing_year and exclude != "year":
        active.append(
            {
                "member": YEAR_DIMENSION,
                "operator": "equals",
                "values": [str(request.signing_year)],
            }
        )
    if request.consideration_type and exclude != "consideration":
        active.append(
            {
                "member": CONSIDERATION_DIMENSION,
                "operator": "equals",
                "values": [request.consideration_type],
            }
        )
    if request.deal_size_band and exclude != "band":
        active.append(
            {
                "member": BAND_DIMENSION,
                "operator": "equals",
                "values": [request.deal_size_band],
            }
        )
    return active


def _group(
    key: str,
    label: str,
    dimension: str,
    request: FacetRequest,
    selected: str | None,
    code_dimension: str | None = None,
) -> FacetGroup:
    """One facet group.

    `code_dimension` is grouped alongside the label where the dimension has a stable
    identifier, so the client can filter by the code rather than the display string.
    """
    rows = cube_query(
        {
            "measures": [COUNT_MEASURE],
            "dimensions": [dimension] + ([code_dimension] if code_dimension else []),
            "filters": _filters(request, exclude=key),
            "order": {COUNT_MEASURE: "desc"},
        }
    )
    values = [
        FacetValue(
            value=str(row[dimension]) if row[dimension] is not None else "unclassified",
            n=int(row[COUNT_MEASURE]),
            selected=selected is not None and str(row[dimension]) == str(selected),
            code=(
                str(row[code_dimension])
                if code_dimension and row.get(code_dimension) is not None
                else None
            ),
            # an absence bucket gets its cause; a real value gets none
            reason=(
                VALUE_REASONS.get(key)
                if (str(row[dimension]) if row[dimension] is not None else "unclassified")
                .lower()
                .strip()
                in UNINFORMATIVE
                else None
            ),
        )
        for row in rows
    ]
    informative = [v for v in values if v.value.lower() not in UNINFORMATIVE]
    unavailable = None
    if values and not informative:
        unavailable = REASONS.get(key, "no values have been loaded for this dimension yet")

    # Only count matters that actually carry a value. Summing every bucket including
    # `unclassified` produced the contradiction in #34: DEAL SIZE reported n=152 directly above
    # prose saying nothing was filterable, because all 152 sat in the unknown bucket.
    filterable_n = sum(v.n for v in informative)

    return FacetGroup(
        key=key,
        label=label,
        values=values,
        total_n=None if unavailable else filterable_n,
        total_basis="" if unavailable else TOTAL_BASIS.get(key, "matters in this slice"),
        inferred=key in INFERRED_GROUPS,
        unavailable=unavailable,
    )


@router.post("/facets", response_model=FacetsResponse)
def facets(request: FacetRequest) -> FacetsResponse:
    try:
        groups = [
            _group(
                "industry",
                "Industry",
                INDUSTRY_DIMENSION,
                request,
                request.folio_industry_label,
                code_dimension=CODE_DIMENSION,
            ),
            _group(
                "year",
                "Signing year",
                YEAR_DIMENSION,
                request,
                str(request.signing_year) if request.signing_year is not None else None,
            ),
            # before Deal size, which is empty: a live axis should not sit under a dead one
            _group(
                "consideration",
                "Consideration",
                CONSIDERATION_DIMENSION,
                request,
                request.consideration_type,
            ),
            _group("band", "Deal size", BAND_DIMENSION, request, request.deal_size_band),
        ]
        selected = cube_query(
            {"measures": [COUNT_MEASURE], "filters": _filters(request, exclude="")}
        )
        unfiltered = cube_query({"measures": [COUNT_MEASURE]})
        deal_point_rows = cube_query({"measures": [DEAL_POINT_COUNT]})
    except CubeUnavailable as unavailable:
        raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    industry_group = next(g for g in groups if g.key == "industry")
    return FacetsResponse(
        corpus=CorpusCounts(
            matters=int(unfiltered[0][COUNT_MEASURE]) if unfiltered else 0,
            deal_points=(int(deal_point_rows[0][DEAL_POINT_COUNT]) if deal_point_rows else 0),
            # "unclassified" is a bucket, not an industry — counting it would overstate coverage
            industries=sum(
                1 for v in industry_group.values if v.n > 0 and v.value.lower() not in UNINFORMATIVE
            ),
        ),
        groups=groups,
        total_n=int(selected[0][COUNT_MEASURE]) if selected else 0,
        unfiltered_n=int(unfiltered[0][COUNT_MEASURE]) if unfiltered else 0,
    )

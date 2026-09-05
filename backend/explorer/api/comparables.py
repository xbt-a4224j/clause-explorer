"""`POST /comparables` — industry filter, then hybrid rank within the filtered set (#18).

**Filter before rank, never after.** Ranking the whole corpus and then dropping out-of-filter
results is the obvious implementation and it is wrong twice over: a request for ten healthcare
comparables can return three because seven of the top ten were filtered away afterwards, and
the scores that survive were normalized against a corpus the user did not ask about. Here the
industry/date filter runs in Postgres first and the hybrid index is built over exactly the
surviving matters, so relevance is relative to the requested slice.

**The filter matches a code, never a display label.** `industries.code` is opaque and stable;
the label is display text that can be retitled. Filtering on the label means a drift from
"Health Care Industry" to "Healthcare" returns zero rows, which reads as *we have no comparable
deals* (#25). #49 removed the hierarchy roll-up that used to sit here — every code the corpus
carries is at the same level, so the descendant walk returned exactly what equality returns.

The response carries the filters that were actually applied, not the ones that were asked
for — they differ when a filter value cannot be resolved, and the resolved-query display (#23,
#26) exists so a domain expert can catch that.

No API key required: matter summaries and the query text come from the committed embedding
cache (#16). An uncached free-text query with no key is a 503 naming the cached count, never a
silent API call and never a bare 500.
"""

from __future__ import annotations

import time

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.api.logging import get_logger
from explorer.api.settings import settings
from explorer.retrieval.embeddings import EmbeddingUnavailable
from explorer.retrieval.hybrid import DEFAULT_ALPHA, HybridIndex

router = APIRouter()
log = get_logger()

# Defined at module scope, not inside the handler: `from __future__ import annotations` plus a
# model defined in a function raises PydanticUndefinedAnnotation.


class ComparablesRequest(BaseModel):
    description: str | None = Field(
        default=None,
        description="Free text describing the deal in front of you. Ranks the filtered set.",
    )
    folio_industry_code: str | None = Field(
        default=None,
        description=(
            "Industry code from the SIC crosswalk. A code, never a display label — see the "
            "module docstring. The field name still says folio_ because it is the wire "
            "contract the frontend reads; the table behind it is `industries` (#49)."
        ),
    )
    deal_size_band: str | None = Field(
        default=None,
        description="Band label as defined in the Cube model. Every matter is 'unknown' today.",
    )
    consideration_type: str | None = Field(
        default=None,
        description=(
            "All Cash / All Stock / Mixed — MAUD's expert label, and the substitute axis for "
            "deal size (#9). The facet rail offers it, so this endpoint must apply it."
        ),
    )
    signed_from: str | None = Field(default=None, description="ISO date, inclusive.")
    signed_to: str | None = Field(default=None, description="ISO date, inclusive.")
    limit: int = Field(default=10, ge=1, le=100)
    alpha: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Hybrid weight; defaults to HYBRID_ALPHA."
    )


class ComparableMatter(BaseModel):
    matter_id: str
    target_name: str | None
    acquirer_name: str | None
    industry: str | None
    is_inferred_industry: bool
    signing_date: str | None
    score: float | None
    vector_score: float | None
    bm25_score: float | None


class AppliedFilters(BaseModel):
    """What actually constrained the result — shown above the answer (#23/#26)."""

    folio_industry_code: str | None
    folio_industry_label: str | None
    deal_size_band: str | None
    consideration_type: str | None
    signed_from: str | None
    signed_to: str | None
    ranked_by: str


class ComparablesResponse(BaseModel):
    matters: list[ComparableMatter]
    candidate_count: int
    returned_count: int
    applied_filters: AppliedFilters


CANDIDATE_SQL = """
SELECT m.id,
       m.target_name,
       m.acquirer_name,
       i.label,
       m.is_inferred_industry,
       to_char(m.signing_date, 'YYYY-MM-DD'),
       concat_ws(' · ',
           m.source_contract_title,
           nullif(concat_ws(' / ', m.target_name, m.acquirer_name), ''),
           i.label,
           to_char(m.signing_date, 'YYYY')
       )
FROM matters m
LEFT JOIN industries i ON i.code = m.industry_code
-- explicit casts: Postgres cannot infer a parameter's type from `$1 IS NULL` alone and
-- raises AmbiguousParameter. Every filter is still a bound parameter, never interpolated.
WHERE (%(industry)s::text IS NULL OR m.industry_code = %(industry)s::text)
  AND (%(signed_from)s::date IS NULL OR m.signing_date >= %(signed_from)s::date)
  AND (%(signed_to)s::date IS NULL OR m.signing_date <= %(signed_to)s::date)
  AND (%(band)s::text IS NULL OR %(band)s::text = 'unknown')
  -- Consideration is MAUD's expert answer to a deal point rather than a column on the matter,
  -- so it filters by existence of that labelled row. Same definition as the Cube dimension the
  -- facet rail counts with; two definitions would let the rail and the list disagree, which is
  -- exactly what happened while this clause was missing.
  AND (%(consideration)s::text IS NULL OR EXISTS (
        SELECT 1 FROM public.deal_points dp
         WHERE dp.matter_id = m.id
           AND dp.deal_point_name = 'Type of Consideration-Answer'
           AND dp.position = %(consideration)s::text))
ORDER BY m.id
"""


def _label_for(conn: psycopg.Connection, code: str | None) -> str | None:
    """The display label for a code, or None when the code is not in the vocabulary."""
    if not code:
        return None
    row = conn.execute("SELECT label FROM industries WHERE code = %s", (code,)).fetchone()
    return str(row[0]) if row else None


@router.post("/comparables", response_model=ComparablesResponse)
def comparables(request: ComparablesRequest) -> ComparablesResponse:
    started = time.perf_counter()
    alpha = DEFAULT_ALPHA if request.alpha is None else request.alpha

    with psycopg.connect(settings.database_url) as conn:
        industry_label = _label_for(conn, request.folio_industry_code)
        if request.folio_industry_code and industry_label is None:
            # fail loudly rather than returning zero rows that read as "no comparable deals"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Industry code {request.folio_industry_code!r} does not exist. "
                    "Zero results and an unknown code look identical to a reader, so this "
                    "is an error rather than an empty list."
                ),
            )
        rows = conn.execute(
            CANDIDATE_SQL,
            {
                "industry": request.folio_industry_code,
                "signed_from": request.signed_from,
                "signed_to": request.signed_to,
                "band": request.deal_size_band,
                "consideration": request.consideration_type,
            },
        ).fetchall()

    applied = AppliedFilters(
        folio_industry_code=request.folio_industry_code,
        folio_industry_label=industry_label,
        deal_size_band=request.deal_size_band,
        consideration_type=request.consideration_type,
        signed_from=request.signed_from,
        signed_to=request.signed_to,
        ranked_by=(
            f"hybrid alpha={alpha}" if request.description else "matter id (no description given)"
        ),
    )

    scored: dict[str, tuple[float, float, float]] = {}
    if request.description and rows:
        # index over the FILTERED set only — see module docstring
        index = HybridIndex([r[0] for r in rows], [r[6] or "" for r in rows])
        try:
            for hit in index.search(request.description, alpha=alpha, limit=request.limit):
                scored[hit.matter_id] = (hit.score, hit.vector_score, hit.bm25_score)
        except EmbeddingUnavailable as unavailable:
            raise HTTPException(status_code=503, detail=str(unavailable)) from unavailable

    if scored:
        ordered = [r for r in rows if r[0] in scored]
        ordered.sort(key=lambda r: scored[r[0]][0], reverse=True)
    else:
        ordered = rows[: request.limit]

    matters = [
        ComparableMatter(
            matter_id=row[0],
            target_name=row[1],
            acquirer_name=row[2],
            industry=row[3],
            is_inferred_industry=bool(row[4]),
            signing_date=row[5],
            score=scored.get(row[0], (None, None, None))[0],
            vector_score=scored.get(row[0], (None, None, None))[1],
            bm25_score=scored.get(row[0], (None, None, None))[2],
        )
        for row in ordered[: request.limit]
    ]

    log.info(
        "comparables",
        folio_industry_code=request.folio_industry_code,
        deal_size_band=request.deal_size_band,
        consideration_type=request.consideration_type,
        signed_from=request.signed_from,
        signed_to=request.signed_to,
        has_description=bool(request.description),
        alpha=alpha,
        candidate_count=len(rows),
        returned_count=len(matters),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )

    return ComparablesResponse(
        matters=matters,
        candidate_count=len(rows),
        returned_count=len(matters),
        applied_filters=applied,
    )

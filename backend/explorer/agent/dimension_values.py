"""The values a dimension actually holds — the vocabulary resolution picks from.

Cube's `/meta` carries names, types and descriptions and NOT values, which is correct: a
dimension's vocabulary is data, not metadata. You get it by querying grouped by that dimension,
which is what this does.

Only closed dimensions belong here. A dimension whose values grow with the corpus — a target
name, a signing date — has no vocabulary to enum-lock and must never be resolved this way; the
caller carries those through verbatim and says so.
"""

from __future__ import annotations

from explorer.api.cube_client import query as cube_query

#: Dimensions with a closed, small, stable value set. Sizes measured 2026-09-06:
#: deal point 92 · industry 14 · consideration 4 · position ~250 across all deal points.
#: `deal_point_name` is the important one — every legally interesting question names a deal
#: point, and until it was resolvable the Ask box answered 0 of 10 real questions.
CLOSED_DIMENSIONS = frozenset(
    {
        "deal_points.deal_point_name",
        "deal_points.position",
        "comparable_deals.label",
        "comparable_deals.consideration_type",
        "comparable_deals.signing_year",
        "industries.label",
    }
)

#: Above this a vocabulary is not sendable as an enum and the dimension is not closed in any
#: useful sense. Nothing in this corpus approaches it; the guard is here so that the day a
#: dimension does, resolution refuses loudly rather than sending a 40k-token prompt.
MAX_VOCABULARY = 500


def dimension_values(dimension: str) -> list[str]:
    """Distinct non-null values, sorted. Empty when the dimension is not closed."""
    if dimension not in CLOSED_DIMENSIONS:
        return []
    rows = cube_query({"dimensions": [dimension], "limit": MAX_VOCABULARY + 1})
    values = sorted({str(r[dimension]) for r in rows if r.get(dimension) is not None})
    return [] if len(values) > MAX_VOCABULARY else values

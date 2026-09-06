"""Question shape — pick the skeleton, then only the deal point.

Measured 2026-09-06 on ten questions a transactional lawyer would actually ask, **0 of 10**
produced an answer to the question asked. The failures share one cause: given a free choice
over eleven measures, the model picks a plausible one that does not answer the question.

    "what percentage of deals is cash-only"       -> comparable_deals.n   (a count, no denominator)
    "what's the largest deal value by dollar"     -> comparable_deals.n   (a count, not a max)
    "what's the ordinary course efforts standard" -> median + p25 + p75 over seven dimensions

A real number, correctly computed, for a question nobody asked — which CLAUDE.md names as the
nastiest failure in the design, because it looks exactly like a right answer.

But almost every "what's market" question has ONE skeleton: count the agreements, grouped by
the answer they gave, filtered to a single deal point. Choosing the shape from a four-value
enum first means the model never picks the measure in that case, and the whole class stops
being reachable rather than being caught downstream.

The division of labour is deliberate: the shape is the cheap decision over four options, and
the deal point is the hard one over 92. Separating them spends the model's attention on the
half that needs it.
"""

from __future__ import annotations

from typing import Any

#: The closed set of shapes. Deliberately four — a fifth would mean a question this corpus
#: answers that none of these covers, and that is a modelling finding worth having rather than
#: an enum to extend quietly.
SHAPES: tuple[str, ...] = ("distribution", "median", "count", "coverage")

DEAL_POINT = "deal_points.deal_point_name"


def _pin(deal_point: str) -> list[dict[str, Any]]:
    return [{"member": DEAL_POINT, "operator": "equals", "values": [deal_point]}]


def selection_for(shape: str, deal_point: str | None) -> dict[str, Any]:
    """The Cube selection this shape means. Raises KeyError for an unknown shape.

    Every shape that reads `numeric_value` or groups by `position` REQUIRES a deal point, and
    refuses without one. Both are the same failure in different clothes: `position` across all
    92 deal points mixes every answer vocabulary in the corpus into a single column, exactly as
    an unscoped percentile mixes months, business days and percent.
    """
    if shape not in SHAPES:
        raise KeyError(f"{shape!r} is not one of {SHAPES}")

    if shape in ("distribution", "median") and not deal_point:
        raise ValueError(
            f"the {shape!r} shape needs a deal point — without one it aggregates across all "
            "92, which mixes unrelated answer vocabularies into one column"
        )

    if shape == "distribution":
        # The workhorse. "6 of 8 had a fiduciary out" is this, and the full answer
        # distribution rather than a headline is what stops it hiding the disagreement.
        assert deal_point
        return {
            "measures": ["deal_points.n"],
            "dimensions": ["deal_points.position"],
            "filters": _pin(deal_point),
        }

    if shape == "median":
        # numeric_n travels with it because a median with no denominator is a figure nobody
        # can weigh, and because REQUIRES_SCOPE would reject the percentile without the pin.
        assert deal_point
        return {
            "measures": ["deal_points.median_numeric_value", "deal_points.numeric_n"],
            "dimensions": [],
            "filters": _pin(deal_point),
        }

    if shape == "coverage":
        # "How many agreements do we even have an answer for on this point" — the denominator
        # question, asked on its own. Thin coverage is a finding, not an empty result.
        return {
            "measures": ["deal_points.n"],
            "dimensions": [],
            "filters": _pin(deal_point) if deal_point else [],
        }

    return {"measures": ["comparable_deals.n"], "dimensions": [], "filters": []}

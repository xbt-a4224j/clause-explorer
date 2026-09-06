"""Question shape, bound to this domain.

The implementation moved to `quorum.agent.shape`. What was here was 105 lines that named
`deal_points.deal_point_name`, `deal_points.position` and `deal_points.n` in four places and
contained no legal logic at all — it builds four Cube selections, and every one of them names
the same three members. The four skeletons and the reasons for them now live in the platform,
where a second corpus gets them without a fork; see that module's docstring for the measurement
(0 of 10 free-form, and `distribution` as DEFAULT worth 7/27 -> 17/27).

This file is the binding: the members come from `quorum.yaml`, so nothing downstream has to
carry a domain around.
"""

from __future__ import annotations

from typing import Any

from quorum.agent.shape import SHAPES, UnscopedShape
from quorum.agent.shape import selection_for as _selection_for

from explorer.domain import DOMAIN

#: The subject axis, kept as a name because parts of the app still spell it out.
DEAL_POINT = DOMAIN.subject_axis

__all__ = ["DEAL_POINT", "SHAPES", "UnscopedShape", "selection_for"]


def selection_for(shape: str, deal_point: str | None) -> dict[str, Any]:
    """The Cube selection this shape means, for this corpus."""
    return _selection_for(DOMAIN, shape, deal_point)

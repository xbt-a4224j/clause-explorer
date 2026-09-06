"""The values a dimension actually holds, bound to this deployment's Cube.

Implementation in `quorum.agent.dimension_values`, including why *which* dimensions are closed
is read from the Cube model's own `meta.closed_vocabulary` rather than a constant — a hardcoded
frozenset here was a second source of truth that nothing kept in step, and renaming a dimension
in YAML would have silently stopped it resolving while looking like the model getting worse.
"""

from __future__ import annotations

from typing import Any

from quorum.agent.dimension_values import MAX_VOCABULARY
from quorum.agent.dimension_values import closed_dimensions as _closed
from quorum.agent.dimension_values import dimension_values as _values

from explorer.api.settings import settings

__all__ = ["MAX_VOCABULARY", "closed_dimensions", "dimension_values"]


def closed_dimensions(meta: dict[str, Any] | None = None) -> frozenset[str]:
    """Members the Cube model declares closed. `meta` is injectable for tests."""
    return _closed(meta, cube_url=settings.cube_api_url)


def dimension_values(dimension: str) -> list[str]:
    """Distinct non-null values, sorted. Empty when the dimension is not closed."""
    return _values(dimension, cube_url=settings.cube_api_url)

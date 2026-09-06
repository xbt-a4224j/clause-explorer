"""The only place this API talks to Cube, bound to this deployment's URL.

The implementation is `quorum.cube.client`. It takes the Cube URL as an argument and reads no
settings, which is what lets the platform be a library rather than an application — and what
the platform's boundary test enforces. This module supplies the URL, so nothing else in the app
has to carry it.

Keeping the module at this path rather than rewriting thirty call sites is deliberate: the
import churn would bury the change that matters in a diff of renames.
"""

from __future__ import annotations

from typing import Any

from quorum.cube.client import CONTINUE_WAIT, MAX_WAITS, CubeUnavailable
from quorum.cube.client import meta as _meta
from quorum.cube.client import query as _query

from explorer.api.settings import settings

__all__ = ["CONTINUE_WAIT", "MAX_WAITS", "CubeUnavailable", "meta", "query"]


def query(payload: dict[str, Any], timeout: float = 20.0) -> list[dict[str, Any]]:
    """Run a Cube selection. Raises `CubeUnavailable` rather than returning an empty result —
    an empty facet rail and a dead semantic layer look identical in the UI."""
    return _query(payload, settings.cube_api_url, timeout)


def meta(timeout: float = 20.0) -> dict[str, Any]:
    """Cube's `/meta` — the vocabulary a selection may draw from, read live rather than
    checked in, so a copy cannot drift from `cube/model/*.yml`."""
    return _meta(settings.cube_api_url, timeout)

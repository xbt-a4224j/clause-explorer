"""NL -> a governed Cube selection, bound to this domain and this deployment.

The implementation is `quorum.agent.select`. Everything that made this file 293 lines lives
there now: the enum-constrained schema, the vocabulary read live from `/meta`, and the scope
guard that refuses a percentile the selection has not pinned to one subject value.

Three constants stopped being constants in the move, and each was a small lie about where the
knowledge lived:

- `SELECTABLE` and `EXCLUDED_MEASURES` are `selectable:` and `excluded_measures:` in
  `quorum.yaml`. They were always a statement about this corpus's Cube model.
- `REQUIRES_SCOPE` was three legal measure names hardcoded here. It is derived from the
  manifest's `numeric_measures` and `subject_axis`, because the rule is "a percentile over a
  column holding several units at once is not a quantity" and never mentioned deal points.

`REQUIRES_SCOPE` is still exported as a mapping so the tests that assert on it keep working,
but it is now computed from the domain rather than typed out.
"""

from __future__ import annotations

from typing import Any

from quorum.agent.select import (
    SELECT_MODEL,
    AgentUnavailable,
    InvalidSelection,
    SelectionCall,
    Vocabulary,
    requires_scope,
    scope_reason,
)
from quorum.agent.select import fetch_vocabulary as _fetch_vocabulary
from quorum.agent.select import select_via_llm as _select_via_llm
from quorum.agent.select import select_with_usage as _select_with_usage
from quorum.agent.select import system_prompt as _system_prompt
from quorum.agent.select import validate_selection as _validate_selection

from explorer.api.settings import settings
from explorer.domain import DOMAIN

__all__ = [
    "EXCLUDED_MEASURES",
    "REQUIRES_SCOPE",
    "SCOPE_REASON",
    "SELECTABLE",
    "SELECT_MODEL",
    "SYSTEM_PROMPT",
    "AgentUnavailable",
    "InvalidSelection",
    "SelectionCall",
    "Vocabulary",
    "fetch_vocabulary",
    "select_via_llm",
    "select_with_usage",
    "validate_selection",
]

#: The cubes and views the agent may select from, and the measure it must never pick — a mean
#: kept beside the median so a reader can see the two diverge, which the agent selecting it
#: would turn into exactly the wrong number.
SELECTABLE = set(DOMAIN.selectable)
EXCLUDED_MEASURES = set(DOMAIN.excluded_measures)

#: Measures meaningless unless the selection is pinned to one deal point. Derived, not typed:
#: the percentiles read a column holding months, business days and percent at once, so unscoped
#: their median evaluates to `4` — which is not a wrong quantity so much as not a quantity.
REQUIRES_SCOPE: dict[str, str] = requires_scope(DOMAIN)

#: Said in this corpus's own units, from the manifest.
SCOPE_REASON = scope_reason(DOMAIN)

SYSTEM_PROMPT = _system_prompt(DOMAIN)


def fetch_vocabulary(cube_meta: dict[str, Any] | None = None) -> Vocabulary:
    """The measures and dimensions a selection may name, read live from Cube's `/meta`.

    Live rather than checked in: a copy drifts from `cube/model/*.yml` silently, and the eval
    grades against exactly this list. A catalog disagreeing with the models turns every
    selection failure into an unfalsifiable argument about which list was right.
    """
    return _fetch_vocabulary(DOMAIN, settings.cube_api_url, cube_meta)


def validate_selection(selection: dict[str, Any], vocabulary: Vocabulary) -> None:
    """The one gate every selection passes before it reaches Cube, schema behaved or not."""
    _validate_selection(selection, vocabulary, DOMAIN)


def select_with_usage(question: str, vocabulary: Vocabulary, api_key: str) -> SelectionCall:
    """The free-form fallback call, with what it cost to make."""
    return _select_with_usage(question, vocabulary, api_key, DOMAIN)


def select_via_llm(question: str, vocabulary: Vocabulary, api_key: str) -> dict[str, Any]:
    """The selection alone, for callers with no cost line to render."""
    return _select_via_llm(question, vocabulary, api_key, DOMAIN)

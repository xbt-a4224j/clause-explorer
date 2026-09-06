"""A constrained chooser for filter VALUES, bound to this app's key.

Implementation and the measurement in `semantic_explorer_base.agent.pick_value`: 14/16 on legal terms of art
with zero false positives, against 12/16 for embeddings with one outright wrong match.

This is the second model call in Ask, and it exists because of an asymmetry the first cannot
fix. Measure and dimension NAMES are enum-locked at decode time, so an invalid name is
unrepresentable; values could not be, so a near-miss returned zero rows — which reads as "we
have no comparable deals" rather than "you named something we do not carry".
"""

from __future__ import annotations

from semantic_explorer_base.agent.pick_value import PICK_MODEL, SYSTEM_PROMPT
from semantic_explorer_base.agent.pick_value import pick_value as _pick_value

from explorer.api.settings import settings

__all__ = ["PICK_MODEL", "SYSTEM_PROMPT", "pick_value"]


def pick_value(
    raw: str,
    candidates: list[str],
    api_key: str | None = None,
    task: str | None = None,
    usage_sink: list[tuple[int, int]] | None = None,
) -> str | None:
    """Map a phrase to exactly one value from the dimension's own vocabulary, or None.

    None rather than an exception when no key is configured, so the caller falls through to its
    own refusal path with the candidates attached instead of surfacing a 500.
    """
    return _pick_value(raw, candidates, api_key or settings.openai_api_key, task, usage_sink)

"""One question -> a governed selection, bound to this domain.

The implementation moved to `semantic_explorer_base.agent.interpret`, along with the prompt, the enum schema
and the reasons for both. This file supplies the two things the platform cannot know: which
corpus it is reading, and where this app's key and Cube live.

`CHOOSE_PROMPT` is assembled from `quorum.yaml`'s nouns rather than written here, and it
assembles byte-identical to the string that was benchmarked at 20/27 — pinned by
`backend/tests/test_interpret_flow.py` and again in the platform's own suite. The prompt IS the
implementation, so that equality is the thing keeping the measurement honest across the move.
"""

from __future__ import annotations

from typing import Any

from semantic_explorer_base.agent.interpret import (
    Interpretation,
    subject_glosses,
)
from semantic_explorer_base.agent.interpret import (
    choose_interpretation as _choose,
)
from semantic_explorer_base.agent.interpret import (
    interpret as _interpret,
)
from semantic_explorer_base.agent.interpret import (
    interpretation_schema as _interpretation_schema,
)
from semantic_explorer_base.agent.prompt import build

from explorer.api.settings import settings
from explorer.domain import DOMAIN

#: The subject axis, spelled out because several call sites still name it.
DEAL_POINT = DOMAIN.subject_axis

#: Assembled, not authored. Identical to the benchmarked string; a test asserts it.
CHOOSE_PROMPT = build(DOMAIN)

__all__ = [
    "CHOOSE_PROMPT",
    "DEAL_POINT",
    "Interpretation",
    "choose_interpretation",
    "deal_point_glosses",
    "interpret",
    "interpretation_schema",
]


def interpretation_schema(
    glosses: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, str]]:
    """The structured-output schema, with this corpus's deal points as the enum.

    The field the model fills in is named `deal_point` here, derived from the manifest's own
    noun. That name is part of what the model reads, so keeping it is what makes the extracted
    call the same call that was benchmarked — the prompt text being byte-identical would not
    have been enough on its own.
    """
    return _interpretation_schema(glosses, DOMAIN)


def deal_point_glosses(values: Any = None) -> dict[str, list[str]]:
    """Each deal point with the answers it takes — the single biggest accuracy lever measured,
    18/20 -> 20/20 on answerable questions. See the platform module for why."""
    return subject_glosses(DOMAIN, values, cube_url=settings.cube_api_url)


def choose_interpretation(
    question: str,
    api_key: str | None = None,
    usage: list[tuple[int, int]] | None = None,
    *,
    glosses: dict[str, list[str]] | None = None,
) -> tuple[str | None, str | None, bool]:
    """Shape and deal point in one enum-constrained call, with a self-check."""
    return _choose(
        question,
        DOMAIN,
        api_key or settings.openai_api_key,
        usage,
        glosses=glosses,
        cube_url=settings.cube_api_url,
    )


def interpret(
    question: str,
    api_key: str | None = None,
    *,
    choose: Any = None,
    usage: list[tuple[int, int]] | None = None,
) -> Interpretation:
    """The selection this question means, or a decline when the corpus cannot answer it."""
    return _interpret(
        question,
        DOMAIN,
        api_key or settings.openai_api_key,
        choose=choose,
        usage=usage,
        cube_url=settings.cube_api_url,
    )

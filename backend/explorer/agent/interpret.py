"""One question -> a governed selection, via two small constrained choices.

The free-form path asks a single model call to choose measures, dimensions and filters at once
from a 29-name vocabulary, and measured 0 of 10 on real questions. This path asks two much
smaller questions instead:

    1. what SHAPE is this?      four options
    2. which DEAL POINT?        92 options, enum-locked, null allowed

Both are enum-constrained, so neither can name something that does not exist, and both are
gradeable offline as label prediction — which the free-form selection never really was, because
"is this the right combination of measures and dimensions" has no single answer key.

Returning `None` is a first-class outcome. "What's the average deal size" has no answer here:
deal value is NULL on all 152 matters. Saying so beats returning a count of agreements, which
is what the free-form path did.
"""

from __future__ import annotations

import json
from typing import Any

from explorer.agent.dimension_values import dimension_values
from explorer.agent.pick_value import PICK_MODEL, pick_value
from explorer.agent.shape import SHAPES, selection_for
from explorer.api.logging import get_logger
from explorer.api.settings import settings

log = get_logger()

#: The picker is handed a whole question, not a phrase, so it needs to be told what to extract.
#: Without this it read "what's the typical tail period" as a phrase to map and returned null,
#: even though `Tail Period Length-Answer` was in front of it.
DEAL_POINT_TASK = (
    "The user asked a question about merger agreements. Choose the ONE ABA deal point the "
    "question is about, from the list. Legal terms of art map to their deal point: 'no-shop', "
    "'fiduciary out', 'MAE carve-out', 'bringdown', 'tail period' all name one. Return null "
    "only if this corpus has no deal point covering the question."
)

# Worked examples, not just definitions. The first version of this prompt gave one line per
# shape and measured 2/10: it returned null for "is knowledge actual or constructive" and
# `count` for a question that named a term. Shape is a judgement about what the ASKER wants,
# and a definition of "distribution" does not convey that a question phrased "how many deals
# carve X out" is still asking for the split.
SHAPE_PROMPT = (
    "Classify a question about a corpus of public-target merger agreements into one shape.\n\n"
    "distribution — the question is about how a negotiated TERM came out across the deals. "
    "This is the usual case. It covers 'what is market for X', 'is X usually A or B', "
    "'how many deals have X', 'do agreements include X', 'what share of deals X' — all of "
    "them want the split of answers for one term, with counts.\n"
    "median — the question wants a typical NUMBER for a term measured in days, months or "
    "percent, e.g. 'what is the typical tail period', 'how long is the matching rights "
    "period'.\n"
    "count — how many agreements are in the corpus, with NO negotiated term named.\n"
    "coverage — how many agreements we even have an answer for on one term.\n\n"
    "Return null ONLY when the corpus of merger agreements cannot answer the question at "
    "all — for example a question about deal value in dollars, which these agreements do "
    "not record. If the question names or implies a negotiated term, it is never null."
)

SHAPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"shape": {"type": ["string", "null"], "enum": [*SHAPES, None]}},
    "required": ["shape"],
    "additionalProperties": False,
}


def classify_shape(
    question: str,
    api_key: str | None = None,
    usage_sink: list[tuple[int, int]] | None = None,
) -> str | None:
    key = api_key or settings.openai_api_key
    if not key:
        return None
    from openai import OpenAI

    response = OpenAI(api_key=key).chat.completions.create(
        model=PICK_MODEL,
        messages=[
            {"role": "system", "content": SHAPE_PROMPT},
            {"role": "user", "content": question},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "shape", "schema": SHAPE_SCHEMA, "strict": True},
        },
    )
    shape = json.loads(response.choices[0].message.content or "{}").get("shape")
    if usage_sink is not None and response.usage:
        usage_sink.append((response.usage.prompt_tokens, response.usage.completion_tokens))
    log.info("question_shape", question=question, shape=shape)
    return shape if shape in SHAPES else None


def interpret(
    question: str,
    api_key: str | None = None,
    *,
    classify: Any = None,
    pick: Any = None,
    values: Any = None,
    usage: list[tuple[int, int]] | None = None,
) -> dict[str, Any] | None:
    """The selection this question means, or None when the corpus cannot answer it.

    The three collaborators are injectable so the pipeline is testable with no key and no
    network — the same contract every other model-touching module here follows.
    """
    usage = usage if usage is not None else []
    classify = classify or (lambda q: classify_shape(q, api_key, usage))
    pick = pick or (lambda raw, cands: pick_value(raw, cands, api_key, task=DEAL_POINT_TASK))
    values = values or dimension_values

    shape = classify(question)
    if shape is None:
        log.info("interpret_declined", question=question, reason="no shape")
        return None

    deal_point = None
    if shape in ("distribution", "median", "coverage"):
        candidates = values("deal_points.deal_point_name")
        deal_point = pick(question, candidates) if candidates else None
        if deal_point is None and shape != "coverage":
            log.info("interpret_declined", question=question, shape=shape, reason="no deal point")
            return None

    selection = selection_for(shape, deal_point)
    log.info("interpret", question=question, shape=shape, deal_point=deal_point)
    return selection

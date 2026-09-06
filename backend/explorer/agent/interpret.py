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

from explorer.agent.pick_value import PICK_MODEL
from explorer.agent.shape import SHAPES, selection_for
from explorer.api.logging import get_logger
from explorer.api.settings import settings

log = get_logger()

#: The subject axis, declared `subject_axis: true` in the Cube model.
DEAL_POINT = "deal_points.deal_point_name"

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


CHOOSE_PROMPT = (
    "You read a question about a corpus of public-target merger agreements and return two "
    "things: the SHAPE of the answer, and which ABA deal point it is about.\n\n"
    "SHAPE\n"
    "distribution — how a negotiated TERM came out across the deals. The usual case. Covers "
    "'what is market for X', 'is X usually A or B', 'how many deals have X', 'do agreements "
    "include X', 'what share of deals X'.\n"
    "median — a typical NUMBER for a term measured in days, months or percent.\n"
    "count — how many agreements, with NO term named.\n"
    "coverage — how many agreements we have an answer for on one term.\n\n"
    "DEAL POINT\n"
    "Terms of art map to their point: 'no-shop', 'fiduciary out', 'MAE carve-out', "
    "'bringdown', 'tail period' each name one. Each point is listed with the answers it "
    "actually takes, which is usually what identifies it.\n\n"
    "Also return `covers_the_question`: true only if the deal point you chose actually answers "
    "what was asked. This corpus records negotiated terms only — it holds no deal values in "
    "dollars, no fee amounts, no adviser names, and no go-shop provisions. Choosing the "
    "closest available point and marking it false is the right response when the taxonomy does "
    "not cover the question."
)


def interpretation_schema(
    glosses: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, str]]:
    """The structured-output schema, and the map back to real deal-point names.

    Pure, so the guarantee it encodes can be asserted without a network call: the deal-point
    enum is built from the corpus's own values, which makes a name the corpus does not carry
    undecodable rather than merely discouraged.

    `strict: true` rejects a `"` inside an enum literal with a 400, and 16 of the 92 ABA names
    contain one — `"Ability to consummate" concept is subject to MAE carveouts`. Sanitised
    here and resolved through the returned map.
    """
    safe = {n.replace('"', "'"): n for n in glosses}
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "shape": {"type": ["string", "null"], "enum": [*SHAPES, None]},
            "deal_point": {"type": ["string", "null"], "enum": [*safe, None]},
            "covers_the_question": {"type": "boolean"},
        },
        "required": ["shape", "deal_point", "covers_the_question"],
        "additionalProperties": False,
    }
    return schema, safe


def choose_interpretation(
    question: str,
    api_key: str | None = None,
    usage: list[tuple[int, int]] | None = None,
    *,
    glosses: dict[str, list[str]] | None = None,
) -> tuple[str | None, str | None, bool]:
    """Shape and deal point, in one enum-constrained call, with a self-check.

    The self-check is structural rather than a sterner prompt, and that distinction was
    measured. Telling the model to be strict about null fixed the four questions the taxonomy
    cannot answer and cost five real answers (20/20 -> 15/20). Asking it to choose and then
    separately state whether the choice covers the question kept 19-20 of the answers AND got
    all four declines: a concrete pairing is easier to audit than caution is to calibrate.

    Naming the missing terms in the prompt would have scored better still and would be
    overfitting — it would not survive a term nobody thought of.
    """
    key = api_key or settings.openai_api_key
    if not key:
        return None, None, False

    from openai import OpenAI

    gloss = glosses if glosses is not None else deal_point_glosses()
    schema, safe = interpretation_schema(gloss)
    listing = "\n".join(f"{n} :: {' | '.join(v)}" for n, v in sorted(gloss.items()))
    response = OpenAI(api_key=key).chat.completions.create(
        model=PICK_MODEL,
        # Not sampled. The same question must give the same selection — a figure a partner
        # cannot reproduce is worth less than one they can. (Temperature 0 narrows the spread
        # and does not eliminate it; three identical runs of this scored 23, 21, 22 of 24.)
        temperature=0,
        messages=[
            {"role": "system", "content": CHOOSE_PROMPT},
            {
                "role": "user",
                "content": f"{question}\n\nDeal points, with the answers each takes:\n{listing}",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "interpretation", "schema": schema, "strict": True},
        },
    )
    out = json.loads(response.choices[0].message.content or "{}")
    if response.usage and usage is not None:
        usage.append((response.usage.prompt_tokens, response.usage.completion_tokens))

    shape = out.get("shape") if out.get("shape") in SHAPES else None
    deal_point = safe.get(out.get("deal_point")) if out.get("deal_point") else None
    covers = bool(out.get("covers_the_question"))
    if not covers:
        deal_point = None
    log.info("interpretation", question=question, shape=shape, deal_point=deal_point, covers=covers)
    return shape, deal_point, covers


def deal_point_glosses(values: Any = None) -> dict[str, list[str]]:
    """Each deal point with the answers it actually takes.

    The single biggest accuracy lever measured. The ABA names are cryptic — `W/N/A/F applies
    to-Answer`, `A/P/C application to-Answer` — while their ANSWERS say plainly what the
    question is: `Actual knowledge | Constructive knowledge`. Adding them took the interpreter
    from 18/20 to 20/20 on answerable questions.

    Free, in the sense that costs nothing new to compute: the same grouping already feeds the
    facet rail. It is not free in tokens — it roughly triples the prompt, from ~1,400 to ~4,300
    — which is $0.0007 a question rather than $0.0002.
    """
    from explorer.api.cube_client import query as cube_query

    rows = (values or cube_query)(
        {
            "dimensions": [DEAL_POINT, "deal_points.position"],
            "measures": ["deal_points.n"],
            "limit": 1000,
        }
    )
    grouped: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        name, position = r.get(DEAL_POINT), r.get("deal_points.position")
        if name and position:
            grouped.setdefault(str(name), []).append((str(position), int(r["deal_points.n"])))
    # the five commonest answers, most frequent first — enough to say what the question IS
    return {n: [p for p, _ in sorted(v, key=lambda t: -t[1])[:5]] for n, v in grouped.items()}


def interpret(
    question: str,
    api_key: str | None = None,
    *,
    choose: Any = None,
    usage: list[tuple[int, int]] | None = None,
    covers: bool | None = None,
) -> dict[str, Any] | None:
    """The selection this question means, or None when the corpus cannot answer it.

    ONE model call making two enum-constrained choices at once, plus a self-check. That
    combination won a measured comparison of six strategies over 24 questions with a written
    answer key (`docs/eval/ask_questions.json`); see `evals/ask_bench.py` for the harness and
    `docs/results/ask-strategies.md` for the numbers.

    Deciding shape and deal point together beat deciding them in sequence, at half the calls
    and half the latency — they are not independent, and knowing a question is about a tail
    period tells you it wants a number.

    `choose` is injectable so the pipeline is testable with no key and no network.
    """
    usage = usage if usage is not None else []
    choose = choose or (lambda q: choose_interpretation(q, api_key, usage))

    chosen = choose(question)
    # A stubbed chooser may return the pair; the real one returns the triple.
    shape, deal_point, *rest = (*chosen, covers) if len(chosen) == 2 else chosen
    covers = rest[0] if rest else covers
    if shape is None:
        log.info("interpret_declined", question=question, reason="no shape")
        return None
    if deal_point is None and shape == "count" and not covers:
        # The demo-killer, caught on the deployed stack: "what's the average deal size in
        # dollars" found no deal point (right — deal value is NULL on all 152 matters), then
        # ran `count` unfiltered and answered 152. A number in reply to a question the corpus
        # cannot answer is worse than a refusal, because it looks like an answer. `count`
        # without a deal point is only legitimate when the model affirms the corpus can answer
        # — "how many agreements are loaded" — which is what `covers` carries.
        log.info("interpret_declined", question=question, shape=shape, reason="count, uncovered")
        return None
    if deal_point is None and shape != "count":
        log.info("interpret_declined", question=question, shape=shape, reason="no deal point")
        return None

    selection = selection_for(shape, deal_point)
    log.info("interpret", question=question, shape=shape, deal_point=deal_point)
    return selection

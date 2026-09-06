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
from dataclasses import dataclass
from typing import Any

from explorer.agent.pick_value import PICK_MODEL
from explorer.agent.shape import SHAPES, selection_for
from explorer.api.logging import get_logger
from explorer.api.settings import settings

log = get_logger()

#: The subject axis, declared `subject_axis: true` in the Cube model.
DEAL_POINT = "deal_points.deal_point_name"


@dataclass(frozen=True)
class Interpretation:
    """What one question was understood to mean.

    A single type rather than three return shapes. This was `dict | None | CANNOT_ANSWER`,
    where the last was a module-level sentinel dict — so every caller had to know that `None`
    and one particular dict meant different things, and the bench had to reverse-engineer the
    shape back out of the selection it was handed.

    The distinction the sentinel carried is real and survives as a field: `cannot_answer` means
    the CORPUS has nothing for this question and a caller must not fall back to a wider path,
    while a null `selection` without it means only that none of the four shapes fit. Conflating
    them is how "what's the average deal size in dollars" came back as 152.
    """

    selection: dict[str, Any] | None = None
    shape: str | None = None
    deal_point: str | None = None
    cannot_answer: bool = False

    def __bool__(self) -> bool:
        return self.selection is not None


# VERBATIM the prompt that was benchmarked, not a tidied version of it.
#
# The first ship was a rewrite: same content, reflowed, with "Return null for BOTH" folded into
# the covers_the_question paragraph instead of standing on its own. It measured 23/24 in the
# harness and then answered "what's the average deal size in dollars" with **152** on the
# deployed stack — the model picked `count` rather than declining, because the null directive
# had stopped being its own instruction.
#
# Benchmarking prompt A and shipping prompt A-prime is not a small sin here: the prompt IS the
# implementation. Changes to this string are a code change and need a re-run, not a tidy-up.
CHOOSE_PROMPT = (
    "You read a question about a corpus of public-target merger agreements and return two "
    "things: the SHAPE of the answer, and which ABA deal point it is about.\n\n"
    "SHAPE\n"
    # DEFAULT is load-bearing. Described merely as "the usual case", the model chose `count` or
    # `coverage` for two thirds of the answerable questions and the app returned n=152 instead
    # of the split. Naming it the default and listing the phrasings took the benchmark from
    # 7/27 to 17/27.
    "distribution — DEFAULT. Use this whenever the question names or implies a negotiated "
    "TERM, however it is phrased. 'How many deals have X', 'do agreements include X', 'is X "
    "usually A or B' and 'what is market for X' are ALL distribution: the answer is the split "
    "of positions with counts. Only use count or coverage when NO term is named.\n"
    "median — a typical NUMBER for a term measured in days, months or percent.\n"
    "count — how many agreements, with NO term named.\n"
    "coverage — how many agreements we have an answer for on one term.\n\n"
    "DEAL POINT\n"
    "Terms of art map to their point: 'no-shop', 'fiduciary out', 'MAE carve-out', "
    "'bringdown', 'tail period' each name one.\n\n"
    "Return null for BOTH when this corpus cannot answer the question — it records negotiated "
    "terms only, and holds no deal values in dollars, no fee amounts, and no adviser names.\n\n"
    # The second reason a question is unanswerable: not absent DATA but absent COMPUTATION.
    # Each answer is one slice on one deal point, so ranking agreements, scoring one overall,
    # or relating two terms on the same agreement cannot be expressed — which is why "which of
    # these agreements is most off-market" came back as 152. Worth 3 of the 27.
    "Return null for BOTH, too, when the question asks to compare agreements with one "
    "another, rank them, score one overall, or find deals where two different terms both "
    "hold. Those are real questions and none of them can be answered here.\n\n"
    "Also return `covers_the_question`: true only if the deal point you chose actually answers "
    "what was asked. Choosing the closest available point and marking it false is the right "
    "response when this taxonomy does not cover the question."
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
) -> Interpretation:
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

    shape, deal_point, covers = choose(question)

    # No shape at all, and the model says the corpus has nothing: final.
    if shape is None:
        if not covers:
            log.info("interpret_cannot_answer", question=question)
            return Interpretation(cannot_answer=True)
        log.info("interpret_declined", question=question, reason="no shape")
        return Interpretation()

    # `count` is the one shape that legitimately needs no deal point — "how many agreements are
    # loaded" — but only when the model affirms the corpus can answer. Without that it ran
    # unfiltered and returned the corpus size in reply to questions about deal value.
    if deal_point is None:
        if shape == "count" and covers:
            pass
        elif shape == "count":
            log.info("interpret_cannot_answer", question=question, shape=shape)
            return Interpretation(cannot_answer=True)
        else:
            log.info("interpret_declined", question=question, shape=shape, reason="no deal point")
            return Interpretation()

    log.info("interpret", question=question, shape=shape, deal_point=deal_point)
    return Interpretation(
        selection=selection_for(shape, deal_point), shape=shape, deal_point=deal_point
    )

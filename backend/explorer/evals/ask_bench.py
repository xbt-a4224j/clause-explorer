"""Which interpretation strategy turns a lawyer's question into the right selection.

Graded against `docs/eval/ask_questions.json`, which is written against the MAUD taxonomy
rather than any implementation, so every strategy is scored on the same answer key. Twenty
questions have a correct deal point; four must be DECLINED, because the corpus genuinely
cannot answer them — deal value is NULL on all 152 matters, MAUD has no go-shop point, no
reverse-termination-fee amount, and no adviser names. Declining those is a right answer, and a
strategy that invents a nearest match for them is worse than one that answers fewer.

Run:  PYTHONPATH=backend python -m explorer.evals.ask_bench
"""

from __future__ import annotations

import json
import pathlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from explorer.agent.dimension_values import dimension_values
from explorer.agent.interpret import DEAL_POINT_TASK, classify_shape
from explorer.agent.pick_value import PICK_MODEL, pick_value
from explorer.agent.select import Vocabulary, fetch_vocabulary, select_with_usage
from explorer.agent.shape import SHAPES
from explorer.api.settings import settings

QUESTIONS = pathlib.Path(__file__).resolve().parents[3] / "docs/eval/ask_questions.json"
DEAL_POINT_MEMBER = "deal_points.deal_point_name"


@dataclass
class Outcome:
    """What one strategy did with one question."""

    deal_point: str | None = None
    shape: str | None = None
    declined: bool = False
    usage: list[tuple[int, int]] = field(default_factory=list)


Strategy = Callable[[str, list[str], Vocabulary], Outcome]


def _client() -> Any:
    """A client that survives a long benchmark.

    Six strategies x 24 questions x 3 trials is 432 calls, some with 4,300-token prompts, and
    the SDK's default of two retries is not enough for that. A rate limit mid-run is a
    measurement problem, not a result: it would silently truncate a trial and make the strategy
    that happened to run last look worse.
    """
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key, max_retries=8, timeout=60.0)


def _chosen_deal_point(selection: dict[str, Any]) -> str | None:
    for f in selection.get("filters") or []:
        if f.get("member") == DEAL_POINT_MEMBER:
            values = f.get("values") or []
            return str(values[0]) if values else None
    return None


# ── strategies ──────────────────────────────────────────────────────────────────────────


def free_form(question: str, points: list[str], vocab: Vocabulary) -> Outcome:
    """The original: one call, free choice over measures, dimensions and filter values."""
    call = select_with_usage(question, vocab, settings.openai_api_key or "")
    return Outcome(
        deal_point=_chosen_deal_point(call.selection),
        usage=[(call.prompt_tokens, call.completion_tokens)],
    )


def shape_then_point(question: str, points: list[str], vocab: Vocabulary) -> Outcome:
    """Two calls: classify the skeleton, then pick the deal point from a 92-value enum."""
    usage: list[tuple[int, int]] = []
    shape = classify_shape(question, settings.openai_api_key, usage)
    if shape is None:
        return Outcome(declined=True, usage=usage)
    dp = pick_value(
        question, points, settings.openai_api_key, task=DEAL_POINT_TASK, usage_sink=usage
    )
    return Outcome(deal_point=dp, shape=shape, declined=dp is None, usage=usage)


def point_then_shape(question: str, points: list[str], vocab: Vocabulary) -> Outcome:
    """Reversed. The deal point is the harder, more informative decision — if the corpus has
    no point for the question, the shape never needed choosing."""
    usage: list[tuple[int, int]] = []
    dp = pick_value(
        question, points, settings.openai_api_key, task=DEAL_POINT_TASK, usage_sink=usage
    )
    if dp is None:
        return Outcome(declined=True, usage=usage)
    shape = classify_shape(question, settings.openai_api_key, usage)
    return Outcome(deal_point=dp, shape=shape, declined=shape is None, usage=usage)


def one_call_both(question: str, points: list[str], vocab: Vocabulary) -> Outcome:
    """One call, BOTH choices enum-constrained in a single schema.

    The interesting hypothesis: shape and deal point are not independent — knowing the question
    is about a tail period tells you it wants a number — so deciding them together may beat
    deciding them in sequence, at half the calls.
    """
    safe = {p.replace('"', "'"): p for p in points}
    schema = {
        "type": "object",
        "properties": {
            "shape": {"type": ["string", "null"], "enum": [*SHAPES, None]},
            "deal_point": {"type": ["string", "null"], "enum": [*safe, None]},
        },
        "required": ["shape", "deal_point"],
        "additionalProperties": False,
    }
    response = _client().chat.completions.create(
        model=PICK_MODEL,
        messages=[
            {"role": "system", "content": COMBINED_PROMPT},
            {"role": "user", "content": question},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "interpretation", "schema": schema, "strict": True},
        },
    )
    out = json.loads(response.choices[0].message.content or "{}")
    u = response.usage
    dp = safe.get(out.get("deal_point")) if out.get("deal_point") else None
    shape = out.get("shape") if out.get("shape") in SHAPES else None
    return Outcome(
        deal_point=dp,
        shape=shape,
        declined=dp is None and shape not in ("count",),
        usage=[(u.prompt_tokens, u.completion_tokens)] if u else [],
    )


COMBINED_PROMPT = (
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
    "'bringdown', 'tail period' each name one.\n\n"
    "Return null for BOTH when this corpus cannot answer the question — it records negotiated "
    "terms only, and holds no deal values in dollars, no fee amounts, and no adviser names."
)


# ── variants of the winner ──────────────────────────────────────────────────────────────
#
# `one_call_both` took 20/24 with two kinds of error, and they want opposite treatment:
#
#   CONFUSION (2)   sibling deal points — "specifically reference COVID-19" went to
#                   "MAE definition includes reference to Target prospects", and the pandemic
#                   carve-out went to the ORDINARY COURSE covenant rather than the NEGATIVE
#                   INTERIM one. Both are cases where the ABA names are cryptic and the ANSWERS
#                   would disambiguate. More context, not more caution.
#
#   OVER-EAGERNESS (2)  go-shop and reverse termination fee do not exist in this taxonomy and
#                   it picked a neighbour anyway. More caution, not more context.
#
# So they are tested separately before being combined, otherwise a combined score cannot say
# which half earned it.


def _one_call(
    question: str,
    points: list[str],
    *,
    prompt: str,
    temperature: float | None = None,
    glosses: dict[str, list[str]] | None = None,
) -> Outcome:
    safe = {p.replace('"', "'"): p for p in points}
    schema = {
        "type": "object",
        "properties": {
            "shape": {"type": ["string", "null"], "enum": [*SHAPES, None]},
            "deal_point": {"type": ["string", "null"], "enum": [*safe, None]},
        },
        "required": ["shape", "deal_point"],
        "additionalProperties": False,
    }
    user = question
    if glosses:
        # The names are cryptic; their ANSWERS say plainly what the question is. Free — this
        # is already computed for the facet rail.
        listing = "\n".join(f"{n} :: {' | '.join(v)}" for n, v in sorted(glosses.items()))
        user = f"{question}\n\nThe deal points, with the answers each one takes:\n{listing}"
    kwargs: dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = _client().chat.completions.create(
        model=PICK_MODEL,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "interpretation", "schema": schema, "strict": True},
        },
        **kwargs,
    )
    out = json.loads(response.choices[0].message.content or "{}")
    u = response.usage
    dp = safe.get(out.get("deal_point")) if out.get("deal_point") else None
    shape = out.get("shape") if out.get("shape") in SHAPES else None
    return Outcome(
        deal_point=dp,
        shape=shape,
        declined=dp is None and shape not in ("count",),
        usage=[(u.prompt_tokens, u.completion_tokens)] if u else [],
    )


#: The default temperature for chat completions is 1.0, which was never set on any of the
#: strategies above. For a classification into a closed vocabulary there is no upside to
#: sampling — the same question should give the same selection, and a figure a partner cannot
#: reproduce is worth less than one they can.
STRICT_PROMPT = COMBINED_PROMPT + (
    "\n\nBe strict about null. This taxonomy is the ABA Public Target Deal Points and it is "
    "CLOSED — it has no entry for go-shop provisions, no fee AMOUNTS of any kind, no deal "
    "values, and no advisers. If the question is about something the list does not cover, "
    "return null for both fields. A neighbouring deal point is not an answer; it is a wrong "
    "answer that looks right."
)


def _glosses() -> dict[str, list[str]]:
    from explorer.api.cube_client import query as cube_query

    rows = cube_query(
        {
            "dimensions": [DEAL_POINT_MEMBER, "deal_points.position"],
            "measures": ["deal_points.n"],
            "limit": 1000,
        }
    )
    out: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        name, pos = r[DEAL_POINT_MEMBER], r["deal_points.position"]
        if name and pos:
            out.setdefault(str(name), []).append((str(pos), int(r["deal_points.n"])))
    # the five commonest answers, most frequent first: enough to say what the question IS
    return {n: [p for p, _ in sorted(v, key=lambda t: -t[1])[:5]] for n, v in out.items()}


GLOSSES: dict[str, list[str]] = {}


def _one_call_confirmed(
    question: str, points: list[str], *, glosses: dict[str, list[str]] | None = None
) -> Outcome:
    """Glosses, plus the model's own check that its pick actually covers the question.

    The gloss variant scored 20/20 on answerable questions and 2/4 on the ones that must be
    declined — it finds everything, including a neighbour for terms the taxonomy does not
    carry. Scolding it in the prompt ("a neighbouring point is a wrong answer") fixed declines
    and cost five real answers.

    Naming the missing terms in the prompt would fix the score and would be overfitting to this
    question set — it would not survive a term I did not think of. So the check is structural
    instead: choose, then state whether the chosen point actually ANSWERS the question. A
    separate field is a separate decision, and the model is markedly better at auditing a
    concrete pairing than at being cautious in the abstract.
    """
    safe = {p.replace('"', "'"): p for p in points}
    schema = {
        "type": "object",
        "properties": {
            "shape": {"type": ["string", "null"], "enum": [*SHAPES, None]},
            "deal_point": {"type": ["string", "null"], "enum": [*safe, None]},
            "covers_the_question": {"type": "boolean"},
        },
        "required": ["shape", "deal_point", "covers_the_question"],
        "additionalProperties": False,
    }
    user = question
    if glosses:
        listing = "\n".join(f"{n} :: {' | '.join(v)}" for n, v in sorted(glosses.items()))
        user = f"{question}\n\nThe deal points, with the answers each one takes:\n{listing}"
    response = _client().chat.completions.create(
        model=PICK_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": CONFIRM_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "interpretation", "schema": schema, "strict": True},
        },
    )
    out = json.loads(response.choices[0].message.content or "{}")
    u = response.usage
    dp = safe.get(out.get("deal_point")) if out.get("deal_point") else None
    if not out.get("covers_the_question"):
        dp = None
    shape = out.get("shape") if out.get("shape") in SHAPES else None
    return Outcome(
        deal_point=dp,
        shape=shape,
        declined=dp is None,
        usage=[(u.prompt_tokens, u.completion_tokens)] if u else [],
    )


CONFIRM_PROMPT = COMBINED_PROMPT + (
    "\n\nAlso return `covers_the_question`: true only if the deal point you chose actually "
    "answers what was asked. Choosing the closest available point and marking it false is the "
    "right response when this taxonomy does not cover the question."
)

STRATEGIES: dict[str, Strategy] = {
    "free-form (1 call)": free_form,
    "shape -> point (2)": shape_then_point,
    "point -> shape (2)": point_then_shape,
    "one call, both (1)": one_call_both,
    "+ temperature 0": lambda q, p, v: _one_call(q, p, prompt=COMBINED_PROMPT, temperature=0),
    "+ answer glosses": lambda q, p, v: _one_call(
        q, p, prompt=COMBINED_PROMPT, temperature=0, glosses=GLOSSES
    ),
    "+ strict null": lambda q, p, v: _one_call(q, p, prompt=STRICT_PROMPT, temperature=0),
    "+ glosses + strict": lambda q, p, v: _one_call(
        q, p, prompt=STRICT_PROMPT, temperature=0, glosses=GLOSSES
    ),
    "+ glosses + confirm": lambda q, p, v: _one_call_confirmed(q, p, glosses=GLOSSES),
}


def grade(trials: int = 1, only: set[str] | None = None) -> None:
    """Score every strategy on the same answer key, `trials` times each.

    Repeated on purpose. The first run of the winning strategy scored 23/24 and I nearly
    reported that; three runs of the identical code at temperature 0 gave 23, 21, 22.
    **Temperature 0 is not determinism** — same prompt, same model, different answer — so a
    single run is a sample, not a measurement. The calibration harness in this repo already
    learned this the expensive way: two identical extraction runs differed by 36 correct out
    of 1,704. Reporting a best-of-n as "the score" is the same error at smaller scale.
    """
    spec = json.loads(QUESTIONS.read_text())["questions"]
    points = dimension_values(DEAL_POINT_MEMBER)
    GLOSSES.update(_glosses())
    vocab = fetch_vocabulary()
    answerable = sum(1 for q in spec if q["deal_point"])
    print(
        f"{len(spec)} questions ({answerable} answerable, {len(spec) - answerable} must "
        f"decline) · {len(points)} deal points in the enum · {trials} trial(s) each\n"
    )

    chosen = {k: v for k, v in STRATEGIES.items() if only is None or k in only}
    results: list[tuple[str, list[int], list[int], float, float, list[str]]] = []
    for name, strategy in chosen.items():
        totals: list[int] = []
        answered: list[int] = []
        cost = 0.0
        started = time.perf_counter()
        misses: list[str] = []
        for trial in range(trials):
            right = declined_right = 0
            for item in spec:
                outcome = strategy(item["q"], points, vocab)
                cost += sum(pt for pt, _ in outcome.usage) * 0.15 / 1e6
                cost += sum(c for _, c in outcome.usage) * 0.60 / 1e6
                expected, got = item["deal_point"], outcome.deal_point
                if expected is None:
                    if got is None:
                        declined_right += 1
                    elif trial == 0:
                        misses.append(f"{item['q'][:40]} -> should decline, got {got[:32]}")
                elif got and expected.lower() in got.lower():
                    right += 1
                elif trial == 0:
                    misses.append(f"{item['q'][:40]} -> {str(got)[:36]}")
            totals.append(right + declined_right)
            answered.append(right)
        results.append(
            (
                name,
                totals,
                answered,
                cost / trials,
                (time.perf_counter() - started) / trials,
                misses,
            )
        )

    print(f"{'strategy':<22} {'total /24':>11} {'answered /20':>13} {'$/run':>8} {'s/run':>7}")
    print("-" * 66)
    for name, totals, answered, cost, secs, _ in sorted(
        results, key=lambda r: sum(r[1]) / len(r[1])
    ):
        mean = sum(totals) / len(totals)
        spread = f"{min(totals)}-{max(totals)}" if len(totals) > 1 else str(totals[0])
        amean = sum(answered) / len(answered)
        print(
            f"{name:<22} {mean:>6.1f} ({spread:<5}) {amean:>8.1f}       {cost:>8.4f} {secs:>7.1f}"
        )
    for name, _t, _a, _c, _s, misses in results:
        if misses:
            print(f"\n  {name} — first trial's misses:")
            for m in misses:
                print(f"    {m}")


if __name__ == "__main__":
    grade()

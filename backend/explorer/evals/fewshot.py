"""Few-shot examples for the calibration extractor, drawn from MAUD itself (#58).

The #44 prompt was zero-shot apart from the option list: a deal point name, 2 to 73 free-text
positions, and 12,000 characters of contract. The model had to infer from the name alone what
an ABA annotator means by, say, "Bringdown Standard" — a distinction MAUD's own annotators were
trained on.

An example here is a real MAUD annotation: a held-in matter's answer, and the byte range the
annotators recorded it at, rendered exactly the way the retrieved passages are rendered so the
example and the question have the same shape.

**The holdout is absolute.** Candidates are filtered by `matter_id <> ALL(holdout)` in SQL, and
a test asserts over the entire 92-deal-point vocabulary that no selected example is a held-out
matter. A leak would turn every figure in `docs/results/calibration.md` into a training-set
number wearing a holdout label, and nothing downstream would look wrong.

Three deliberate limits, each with its cost:

* **Two examples.** They are paid for on all ~1,700 calls; a third buys a third more prompt.
* **Clause-scale spans only** (200 to 3,000 characters). MAUD's span lengths have a median of
  4,658 and a 90th percentile of 238,949 — for holistic deal points the "span" is most of the
  agreement, and pasting one in would be pasting a table of contents. The cost is that 12 of
  the 92 deal points have no anchored held-in span at all and stay zero-shot; they are counted
  in the report rather than filled with an example from a different question.
* **Shortest span per answer.** Deterministic and cheap, at the cost of biasing examples toward
  the tersest drafting of each position.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg

from explorer.api.settings import settings
from explorer.evals.context import Passage, render

# Below this a "span" is a fragment; above it, it stops being clause-scale. The upper bound is
# lower than the app's `max_clause_chars` (6,000) because two examples ride on every call.
EXAMPLE_MIN_CHARS = 200
EXAMPLE_MAX_CHARS = 3000
EXAMPLES_PER_DEAL_POINT = 2

# A quote long enough to be evidence and short enough to be a sentence.
QUOTE_MIN_CHARS = 60
QUOTE_MAX_CHARS = 400

CANDIDATE_SQL = """
SELECT d.matter_id, d.position, d.source_span_start, d.source_span_end
  FROM deal_points d
 WHERE d.deal_point_name = %(name)s
   AND d.span_kind = 'anchored'
   AND d.source_span_start IS NOT NULL
   AND d.source_span_end IS NOT NULL
   AND NOT (d.matter_id = ANY(%(holdout)s))
   AND d.source_span_end - d.source_span_start BETWEEN %(low)s AND %(high)s
 ORDER BY d.position, d.source_span_end - d.source_span_start, d.matter_id
"""


@dataclass(frozen=True)
class Example:
    matter_id: str
    position: str
    start: int
    end: int
    excerpt: str
    quote: str


def leading_sentence(excerpt: str, low: int = QUOTE_MIN_CHARS, high: int = QUOTE_MAX_CHARS) -> str:
    """A verbatim opening sentence of the excerpt.

    Verbatim because the example answer has to satisfy the rule the model's answer is graded
    by — locatable in the source text by substring search. A tidied-up paraphrase would teach
    the model that a near-quote is acceptable, and near-quotes are exactly what the
    quote-verification step exists to catch.
    """
    window = excerpt[: high + 1]
    stop = window.find(". ", low)
    if stop != -1:
        return excerpt[: stop + 1]
    if len(excerpt) <= high:
        return excerpt
    cut = excerpt.rfind(" ", low, high)
    return excerpt[: cut if cut != -1 else high]


def choose(
    rows: list[tuple[str, str, int, int]], limit: int = EXAMPLES_PER_DEAL_POINT
) -> list[tuple[str, str, int, int]]:
    """Round-robin across distinct answers, taking the shortest span for each.

    Two examples that both answer "No" is a prompt that argues for "No" before the contract is
    read. Rows arrive ordered by (position, span length, matter_id), so this is deterministic.
    """
    by_position: dict[str, list[tuple[str, str, int, int]]] = {}
    for candidate in rows:
        by_position.setdefault(candidate[1], []).append(candidate)

    chosen: list[tuple[str, str, int, int]] = []
    depth = 0
    while len(chosen) < limit:
        added = False
        for candidates in by_position.values():
            if depth < len(candidates) and len(chosen) < limit:
                chosen.append(candidates[depth])
                added = True
        if not added:
            break
        depth += 1
    return chosen


def select_examples(
    deal_point_names: list[str],
    holdout_matter_ids: list[str],
    data_root: Path,
    dsn: str | None = None,
    limit: int = EXAMPLES_PER_DEAL_POINT,
) -> dict[str, list[Example]]:
    """Examples per deal point, read from MAUD's annotations on held-in matters only.

    One pass over the vocabulary, caching contract text by matter: the same held-in agreement
    is frequently the shortest-span example for several deal points, and these files run to
    hundreds of kilobytes each.
    """
    selected: dict[str, list[Example]] = {}
    texts: dict[str, str] = {}
    with psycopg.connect(dsn or settings.database_url) as conn:
        sources: dict[str, str] = dict(
            conn.execute("SELECT id, source_file FROM matters").fetchall()
        )
        for name in deal_point_names:
            rows = conn.execute(
                CANDIDATE_SQL,
                {
                    "name": name,
                    "holdout": holdout_matter_ids,
                    "low": EXAMPLE_MIN_CHARS,
                    "high": EXAMPLE_MAX_CHARS,
                },
            ).fetchall()
            examples: list[Example] = []
            for matter_id, position, start, end in choose(list(rows), limit=limit):
                if matter_id not in texts:
                    source_file = sources.get(matter_id)
                    if not source_file:
                        continue
                    path = data_root / source_file
                    if not path.is_file():
                        continue
                    texts[matter_id] = path.read_text(encoding="utf-8", errors="replace")
                excerpt = texts[matter_id][start:end]
                if not excerpt:
                    continue
                examples.append(
                    Example(
                        matter_id=matter_id,
                        position=position,
                        start=start,
                        end=end,
                        excerpt=excerpt,
                        quote=leading_sentence(excerpt),
                    )
                )
            selected[name] = examples
    return selected


def as_messages(examples: list[Example], options: dict[str, str]) -> list[dict[str, str]]:
    """Chat turns: the excerpt as a user message, the annotator's answer as the assistant's.

    The answer is the *option id*, because that is what the schema accepts under `strict: true`;
    an example answering with the free-text position would demonstrate a shape the API rejects.
    An example whose position is not in the option map is dropped rather than answered with an
    id that decodes to nothing.
    """
    by_position = {position: key for key, position in options.items()}
    messages: list[dict[str, str]] = []
    for example in examples:
        option_id = by_position.get(example.position)
        if option_id is None:
            continue
        passage = Passage(example.start, example.end, example.excerpt)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Labelled example from a different agreement ({example.matter_id}):\n"
                    f"{render([passage])}"
                ),
            }
        )
        # json.dumps would be equivalent; written out so the demonstrated shape is visible in
        # the source rather than assembled.
        quote = example.quote.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        messages.append(
            {"role": "assistant", "content": f'{{"position": "{option_id}", "quote": "{quote}"}}'}
        )
    return messages

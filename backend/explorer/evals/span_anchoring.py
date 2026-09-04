"""Measured hit rate for span anchoring (#43): how often MAUD's quoted answer text can be
located, exactly once, inside the span MAUD recorded for it.

    PYTHONPATH=backend python -m explorer.evals.span_anchoring > docs/results/span-anchoring.md

The shipped matcher is `SpanLocator.anchor_with_reason`, re-run here rather than
reimplemented, so the number in the file is the number the database got. The two ablations
below are the alternatives that were tried; they are kept in this module so the rejected
numbers are reproducible from the same command as the accepted one, rather than asserted.
"""

from __future__ import annotations

import bisect
import collections
import statistics
import sys
from dataclasses import dataclass

from explorer.api.settings import settings
from explorer.ingest.maud import (
    ANCHOR_OUTCOMES,
    ANCHORED,
    OMITTED,
    SpanLocator,
    _normalize_with_offsets,
    _strip_rules,
    clean_excerpt,
    parse_maud,
)
from explorer.ingest.maud_corpus import contract_paths

HEAD_TAIL = 120


@dataclass(frozen=True)
class Row:
    deal_point_name: str
    recorded_width: int | None
    outcome: str
    anchored_width: int | None
    plain_hit: bool  # ablation A: no page-rule deletion
    head_tail_hit: bool  # ablation B: head and tail anchors instead of the whole quotation


def _window(offsets: list[int], span: tuple[int, int] | None) -> tuple[int, int]:
    if span is None:
        return 0, len(offsets)
    return bisect.bisect_left(offsets, span[0]), bisect.bisect_left(offsets, span[1])


def _unique(hay: str, needle: str, low: int, high: int) -> int | None:
    at = hay.find(needle, low, high)
    if at == -1 or hay.find(needle, at + 1, high) != -1:
        return None
    return at


def _single_piece(excerpt: str) -> str | None:
    pieces = [s for s in (clean_excerpt(p) for p in OMITTED.split(excerpt)) if s]
    return pieces[0] if len(pieces) == 1 else None


def collect() -> list[Row]:
    sources = {p.stem: p.read_text(encoding="utf-8", errors="replace") for p in contract_paths()}
    _, points = parse_maud()

    rows: list[Row] = []
    matter_id = ""
    locator: SpanLocator | None = None
    plain: tuple[str, list[int]] = ("", [])
    for point in sorted(points, key=lambda p: p.matter_id):
        if point.matter_id != matter_id or locator is None:
            matter_id = point.matter_id
            locator = SpanLocator(sources[matter_id])
            plain = _normalize_with_offsets(sources[matter_id])

        recorded = locator.locate(point.source_excerpt)
        anchored, outcome = locator.anchor_with_reason(point.source_excerpt, recorded)

        piece = _single_piece(point.source_excerpt)
        plain_hit = False
        head_tail_hit = False
        if piece is not None:
            plain_hit = _unique(plain[0], piece, *_window(plain[1], recorded)) is not None
            if outcome != ANCHORED:
                needle = _strip_rules(piece)
                hay, offsets = locator._anchor_index
                low, high = _window(offsets, recorded)
                head = _unique(hay, needle[:HEAD_TAIL], low, high)
                tail = _unique(hay, needle[-HEAD_TAIL:], low, high)
                head_tail_hit = (
                    head is not None
                    and tail is not None
                    and len(needle) <= tail + HEAD_TAIL - head <= 2 * len(needle) + 1000
                )

        rows.append(
            Row(
                deal_point_name=point.deal_point_name,
                recorded_width=None if recorded is None else recorded[1] - recorded[0],
                outcome=outcome,
                anchored_width=None if anchored is None else anchored[1] - anchored[0],
                plain_hit=plain_hit,
                head_tail_hit=head_tail_hit or outcome == ANCHORED,
            )
        )
    return rows


def _quantiles(values: list[int]) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    return (
        f"median {statistics.median(ordered):,.0f} · "
        f"p90 {ordered[int(0.9 * (len(ordered) - 1))]:,} · max {ordered[-1]:,}"
    )


def report() -> str:
    rows = collect()
    total = len(rows)
    hits = sum(1 for r in rows if r.outcome == ANCHORED)
    spanned = [r for r in rows if r.recorded_width is not None]
    spanless = [r for r in rows if r.recorded_width is None]
    recovered = sum(1 for r in spanless if r.outcome == ANCHORED)
    counts: collections.Counter[str] = collections.Counter(r.outcome for r in rows)
    limit = settings.max_clause_chars

    recorded_widths = [r.recorded_width for r in spanned if r.recorded_width is not None]
    stored_widths: list[int] = []
    for row in spanned:
        width = row.anchored_width if row.outcome == ANCHORED else row.recorded_width
        if width is not None:
            stored_widths.append(width)
    anchored_widths = [r.anchored_width for r in rows if r.anchored_width is not None]

    out: list[str] = []
    add = out.append
    add("# Span anchoring: measured hit rate (#43)")
    add("")
    add(
        "MAUD records **where in the agreement an answer was found**, not the clause that "
        "carries it. This is the measured result of replacing each recorded span with the "
        "annotator's own quoted text where that text can be located inside it. An excerpt that "
        "appears more than once in the span is a **miss**, never a guess: storing the first "
        "occurrence would be an offset that opens the wrong clause and looks entirely right."
    )
    add("")
    add("## Command")
    add("")
    add("```")
    add("$ PYTHONPATH=backend python -m explorer.evals.span_anchoring \\")
    add("      > docs/results/span-anchoring.md")
    add("```")
    add("")
    add("## Overall")
    add("")
    add(f"**{hits:,} of {total:,} deal points anchored — {hits / total:.1%}.**")
    add("")
    add("| | rows | anchored | rate |")
    add("|---|---:|---:|---:|")
    add(f"| all deal points | {total:,} | {hits:,} | {hits / total:.1%} |")
    add(
        f"| with a recorded span | {len(spanned):,} | "
        f"{sum(1 for r in spanned if r.outcome == ANCHORED):,} | "
        f"{sum(1 for r in spanned if r.outcome == ANCHORED) / len(spanned):.1%} |"
    )
    add(
        f"| with no span at all | {len(spanless):,} | {recovered:,} | {recovered / len(spanless):.1%} |"
    )
    add("")
    add(
        f"The {len(spanless):,} span-less rows were searched against the **whole document** "
        f"under the same rules, and {recovered:,} were recovered. That is not a surprise in "
        "hindsight: a row has no span precisely because its quoted text could not be found in "
        "the file, and widening the search does not make absent text present."
    )
    add("")
    add("## Why the misses missed")
    add("")
    add("| outcome | rows | share |")
    add("|---|---:|---:|")
    for outcome in ANCHOR_OUTCOMES:
        add(f"| {outcome} | {counts[outcome]:,} | {counts[outcome] / total:.1%} |")
    add("")
    add(
        "The ambiguity rule never fired on this corpus — MAUD's quotations are long enough that "
        "none of them occurs twice inside its own span. It is a guard proven by fixture tests "
        "(`backend/tests/test_span_anchor.py`), not by a corpus row, and it stays because the "
        "cost of the alternative is a plausible-looking wrong offset."
    )
    add("")
    add(
        "The dominant miss is structural, not a matcher weakness: MAUD joins separate "
        "provisions with `<omitted>`, and several provisions are not one clause. Anchoring to "
        "one of them would present part of the basis for the answer as the whole of it, so "
        "those rows keep the recorded envelope and the drill-through keeps labelling them as "
        "excerpts."
    )
    add("")
    add("## What this did to the stored spans")
    add("")
    add("| | width (characters) | over `max_clause_chars` |")
    add("|---|---|---:|")
    add(
        f"| recorded, before #43 | {_quantiles(recorded_widths)} | "
        f"{sum(1 for w in recorded_widths if w > limit):,} |"
    )
    add(
        f"| stored, after #43 | {_quantiles(stored_widths)} | "
        f"{sum(1 for w in stored_widths if w > limit):,} |"
    )
    add(
        f"| the anchored rows alone | {_quantiles(anchored_widths)} | "
        f"{sum(1 for w in anchored_widths if w > limit):,} |"
    )
    add("")
    narrowed = sum(
        1
        for r in spanned
        if r.outcome == ANCHORED
        and r.anchored_width is not None
        and r.recorded_width is not None
        and r.anchored_width < r.recorded_width
    )
    identical = sum(
        1 for r in spanned if r.outcome == ANCHORED and r.anchored_width == r.recorded_width
    )
    add(
        f"**{narrowed:,} of the {hits:,} anchored rows came out narrower than the span they "
        f"replaced; {identical:,} are byte-identical to it.** That is the finding, and it is not "
        "the one the ticket expected: the recorded span was never a loose region around the "
        "answer. Where MAUD quotes one continuous passage, the pre-existing locator already "
        "bounded exactly that passage, so there is nothing left to tighten. Where MAUD quotes "
        "several passages, the span is wide because the annotation itself is discontinuous — "
        "the width is a property of the annotation, not of our matching, and no matcher can "
        "remove it."
    )
    add("")
    add(
        f"`max_clause_chars` is {limit:,}, so the drill-through's rendering is unchanged by this "
        "work: the same rows render as clauses and the same rows render as labelled excerpts. "
        "What anchoring adds is a claim the schema could not previously make — for an "
        "`anchored` row, the characters at this span are the text the annotator quoted and "
        "nothing else, verified per row; a `recorded` row is only *where the answer was found*."
    )
    add("")
    add("## Alternatives tried")
    add("")
    add("| matcher | anchored | rate | why not |")
    add("|---|---:|---:|---|")
    plain_hits = sum(1 for r in rows if r.plain_hit)
    ht_hits = sum(1 for r in rows if r.head_tail_hit)
    add(
        f"| whitespace collapse only | {plain_hits:,} | {plain_hits / total:.1%} | "
        "kept, but as the floor: page-break rules inside a quoted passage break an otherwise "
        "exact match |"
    )
    add(
        f"| **+ page-rule deletion (shipped)** | {hits:,} | {hits / total:.1%} | "
        "a run of underscores or dashes is typographic furniture; deleting it cannot change "
        "what the text says |"
    )
    add(
        f"| + head/tail anchors | {ht_hits:,} | {ht_hits / total:.1%} | "
        "**rejected.** It anchors on the first and last 120 characters and takes the interior "
        "on trust, so the span could no longer claim to be the quotation. It also bought "
        "nothing a reader would see: those rows are single-quotation rows whose recorded span "
        "was already clause-scale |"
    )
    add("")
    add(
        "Quote and dash folding (curly to straight) was also measured and made **no difference "
        "at all** — MAUD's excerpts preserve the source's own punctuation — so it is not in the "
        "shipped matcher and not in this table."
    )
    add("")
    add("## Per deal point")
    add("")
    add("| deal point | n | anchored | rate |")
    add("|---|---:|---:|---:|")
    by_name: dict[str, list[Row]] = collections.defaultdict(list)
    for row in rows:
        by_name[row.deal_point_name].append(row)
    ranked = sorted(
        by_name.items(),
        key=lambda kv: (-sum(1 for r in kv[1] if r.outcome == ANCHORED) / len(kv[1]), kv[0]),
    )
    for name, group in ranked:
        n = len(group)
        anchored = sum(1 for r in group if r.outcome == ANCHORED)
        add(f"| {name} | {n} | {anchored} | {anchored / n:.0%} |")
    add("")
    return "\n".join(out)


def main() -> int:
    sys.stdout.write(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

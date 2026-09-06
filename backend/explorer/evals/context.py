"""What the calibration extractor is shown, and where in the document it came from (#58).

#28 and #44 sent `contract_text[:12000]`. Measured on `contract_10` that is 1.6% of the
agreement: 733,317 characters, of which the model saw 12,000. The MAE definition the first
Label-queue card asks about first appears at character 328,710, and the phrase "ability to
consummate" does not occur inside the window at all. The model answered from the recitals
because a recital was the only thing in front of it. So the published "5 of 90 clear the 0.70
gate" measured, in substantial part, an extractor that was never shown the relevant text.

This module replaces the prefix with **retrieved passages**, reusing `retrieval/hybrid.py`
rather than adding a second retriever: the document is split into overlapping windows, those
windows are the corpus, and `HybridIndex` ranks them by the same normalized BM25 + vector blend
the comparable-deal ranking uses. `alpha` therefore means here exactly what it means there.

Two properties are load-bearing and both are pinned by tests:

* **The budget is unchanged at 12,000 characters.** What differs between the control run and
  this one is *which* 12,000 characters, not how many. A larger window would confound the
  comparison with an ordinary context-length effect, and the finding would no longer be about
  what the model was shown.
* **Offsets are whole-document offsets.** A passage carries the byte range it was cut from, and
  a quote is located inside a passage and then mapped back, so `span_start`/`span_end` mean the
  same thing they meant when the window started at zero. The quote-verification step is
  untouched: located by substring search, or recorded absent.

`prefix_passages` keeps the old behaviour expressible in the same code path, so the control is
re-runnable rather than merely remembered.
"""

from __future__ import annotations

from dataclasses import dataclass

from explorer.retrieval.embeddings import EmbeddingCache
from explorer.retrieval.hybrid import DEFAULT_ALPHA, HybridIndex

# The window the model gets, unchanged from #44 so the before/after differs in content only.
CONTEXT_CHARS = 12000

# A passage is roughly a page of a merger agreement. Long enough that a defined term arrives
# with the sentence that qualifies it; short enough that eight of them fit in the budget.
PASSAGE_CHARS = 1500
# Overlap of 500 characters, so a sentence sitting on a window boundary survives whole in the
# neighbouring window. Without it a retrievable answer can be split across two passages and
# rank below both.
PASSAGE_STRIDE = 1000

# One deal point's position vocabulary is 8,512 characters. Pasted whole into the query it
# dominates the BM25 term counts and the deal point being asked about stops mattering.
QUERY_CHARS = 1000


@dataclass(frozen=True)
class Passage:
    """A byte range of a contract and the text at it. `text == contract[start:end]`, always."""

    start: int
    end: int
    text: str


def split_passages(
    text: str, size: int = PASSAGE_CHARS, stride: int = PASSAGE_STRIDE
) -> list[Passage]:
    """Overlapping fixed-width windows covering the whole document.

    Fixed width rather than paragraph-aware: MAUD's contract text is machine-extracted from
    EDGAR filings and its blank lines mark page breaks and table cells at least as often as they
    mark paragraphs, so a paragraph splitter here would be inventing structure the source does
    not carry.
    """
    if not text:
        return []
    passages: list[Passage] = []
    start = 0
    while True:
        end = min(start + size, len(text))
        passages.append(Passage(start, end, text[start:end]))
        if end == len(text):
            return passages
        start += stride


def prefix_passages(text: str, budget: int = CONTEXT_CHARS) -> list[Passage]:
    """The control: the first `budget` characters, as one passage. Exactly what #44 sent."""
    end = min(budget, len(text))
    return [Passage(0, end, text[:end])]


def retrieval_query(
    deal_point_name: str, allowed_positions: list[str], limit: int = QUERY_CHARS
) -> str:
    """The deal point's name, then as much of its answer vocabulary as fits.

    The vocabulary is in the query because the answers are where the domain words are: the name
    "Pandemic or other public health event: Specific reference to COVID-19" is already good
    query text, but "General economic and financial conditions (Y/N)" is not, and its positions
    ("Yes", "No") add nothing while a fuller vocabulary like
    "Accurate in all material respects" names the exact language to look for. Whole positions
    are kept or dropped, never cut mid-phrase.
    """
    query = deal_point_name
    seen: set[str] = set()
    for position in allowed_positions:
        if position in seen:
            continue
        seen.add(position)
        candidate = f"{query} · {position}"
        if len(candidate) > limit:
            continue
        query = candidate
    return query


def merge(passages: list[Passage], text: str) -> list[Passage]:
    """Document order, with overlapping or touching ranges collapsed into one.

    Adjacent windows share `size - stride` characters. Sending both spends the budget on text
    the model has already read, and renders the same sentence twice under two different
    character ranges, which is the opposite of what the ranges are for.
    """
    ordered = sorted(passages, key=lambda p: (p.start, p.end))
    merged: list[Passage] = []
    for passage in ordered:
        if merged and passage.start <= merged[-1].end:
            previous = merged[-1]
            if passage.end <= previous.end:
                continue
            merged[-1] = Passage(previous.start, passage.end, text[previous.start : passage.end])
        else:
            merged.append(passage)
    return merged


def locate(
    passages: list[Passage], contract_text: str, quote: str
) -> tuple[int | None, int | None]:
    """Where the model's quote sits **in the whole document**, or nowhere.

    Searched inside the passages first, because that is the text the model actually read, and
    the passage's own start is what turns a within-window offset into a document offset. The
    fallback over the full document is belt and braces: it cannot fire on a quote the model
    copied from what it was shown, and if it does fire the range is still a real byte range.

    Unchanged in kind from #28: a substring search, or absent. Never a trusted offset from the
    model.
    """
    if not quote:
        return None, None
    for passage in passages:
        found = passage.text.find(quote)
        if found != -1:
            return passage.start + found, passage.start + found + len(quote)
    found = contract_text.find(quote)
    if found == -1:
        return None, None
    return found, found + len(quote)


def render(passages: list[Passage]) -> str:
    """The user message: each passage under the character range it was cut from.

    The ranges are shown rather than stripped because the excerpts are non-contiguous, and a
    model handed three disjoint pieces of a contract with no marks between them will read them
    as one continuous passage and reason about a sentence boundary that does not exist.
    """
    return "\n\n".join(f"[chars {p.start}-{p.end}]\n{p.text}" for p in passages)


class PassageIndex:
    """One contract, split into passages and indexed with `HybridIndex`.

    Built once per matter and reused across that matter's ~90 deal points. Rebuilding it per
    deal point would re-embed several hundred passages for identical vectors, which is 90x the
    embedding bill for no change in the result.
    """

    def __init__(
        self,
        text: str,
        cache: EmbeddingCache | None = None,
        size: int = PASSAGE_CHARS,
        stride: int = PASSAGE_STRIDE,
    ) -> None:
        self.text = text
        self.passages = split_passages(text, size=size, stride=stride)
        self.index = HybridIndex(
            [f"p{i:05d}" for i in range(len(self.passages))],
            [p.text for p in self.passages],
            cache=cache,
        )
        self._by_id = {f"p{i:05d}": p for i, p in enumerate(self.passages)}

    def search(
        self, query: str, budget: int = CONTEXT_CHARS, alpha: float = DEFAULT_ALPHA
    ) -> list[Passage]:
        """The highest-ranked passages that fit in `budget`, in document order.

        Greedy over the ranking, skipping a passage that would overflow rather than stopping at
        it — the last window of a document is short, and stopping would leave budget unspent for
        no reason. Ties and skips are deterministic because the ranking is.
        """
        wanted = max(1, budget // max(1, PASSAGE_STRIDE) + 8)
        chosen: list[Passage] = []
        used = 0
        for scored in self.index.search(query, alpha=alpha, limit=wanted):
            candidate = merge([*chosen, self._by_id[scored.matter_id]], self.text)
            length = sum(p.end - p.start for p in candidate)
            if length > budget:
                continue
            chosen, used = candidate, length
            if used == budget:
                break
        return chosen

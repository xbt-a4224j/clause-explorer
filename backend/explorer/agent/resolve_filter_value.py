"""Filter-*value* resolution — the nastiest failure mode in the design (#25).

Measure and dimension *names* can be locked with a structured-output enum (#24): the model
either emits `comparable_deals.label` or the call is malformed at decode time. Filter *values*
cannot be enum-locked the same way, because they are free text describing something in the
corpus — the model may emit `"Health Care"` when the data holds `"Health Care Industry"`. That
mismatch returns **zero rows**, which looks exactly like "no comparable deals" and is
indistinguishable from a genuinely thin corpus unless something resolves the value first.

The ladder is **two** tiers, in order, first match wins:

1. **Exact** — case/whitespace-insensitive match against an industry label the corpus carries.
2. **Embedding nearest** — cosine similarity against those same labels, using the
   content-addressed cache (#16), so this runs with no API key against text already warmed.

It was three until #49. The middle rung was an alias table loaded from the ontology's
`skos:altLabel`s; the ontology is gone, and with 14 industry labels in the corpus an alias
tier was matching nothing the embedding tier did not already reach.

Below the similarity floor, or with no vectors at all, resolution **fails loudly**:
`UnresolvedFilterValue` carrying the candidate list. A caller returning `[]` instead is the bug
this module exists to prevent — an empty result set and an unresolved filter value must never
look the same to whoever reads the response.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from psycopg import Connection

from explorer.api.logging import get_logger
from explorer.retrieval.embeddings import EmbeddingCache, EmbeddingUnavailable

log = get_logger()

# Measured against this corpus's actual industry labels (not tuned against a labelled
# benchmark — see #28 for that discipline applied to extraction):
#   'healthcare'                   -> Health Care Industry            0.602  (real hit)
#   'manufacturing'                -> Manufacturing Industry          0.764  (real hit)
#   'financial services'           -> Finance and Insurance Services  0.566  (real hit)
#   'not a real industry at all'   -> Real Estate, Rental and Leasing 0.493  (false positive)
#   'medical devices' / 'life sciences' / 'pharma' -> 0.35-0.43       (real near-misses,
#       but the 256-dim shortened embedding is not confident enough to trust)
# At any floor below ~0.55, the nonsense phrase resolves to a real industry — a silent wrong
# answer, which CLAUDE.md names as the worst failure mode this module exists to prevent. 0.55
# clears every observed real hit and refuses everything below it, including near-misses that
# arguably deserved to resolve. That is a deliberate trade: a false refusal still fails loud
# with candidates and costs a retry; a false resolution looks like a right answer.
SIMILARITY_FLOOR = 0.55


@dataclass(frozen=True)
class Resolution:
    raw: str
    resolved: str
    method: str  # "exact" | "embedding"
    matter_count: int
    similarity: float | None = None


class UnresolvedFilterValue(RuntimeError):
    """No tier resolved the value. Carries what the corpus actually offers instead of a guess."""

    def __init__(self, raw: str, candidates: list[str]) -> None:
        self.raw = raw
        self.candidates = candidates
        super().__init__(
            f"{raw!r} does not match any industry in the corpus. Closest available: "
            f"{', '.join(candidates[:8])}."
        )


def _matter_count(conn: Connection, label: str) -> int:
    row = conn.execute(
        "SELECT count(*) FROM matters m JOIN industries i ON i.code = m.industry_code "
        "WHERE i.label = %s",
        (label,),
    ).fetchone()
    return int(row[0]) if row else 0


def _industry_labels(conn: Connection) -> list[str]:
    """The closed vocabulary this resolves against — labels actually used on `matters`, which
    is 14 of the crosswalk's rows, not every row in it. Mirrors `warm_cache.INDUSTRY_LABEL_SQL`;
    an industry nothing is tagged with must not be resolvable, because filtering on it returns
    zero rows that read as "no comparable deals"."""
    rows = conn.execute(
        "SELECT DISTINCT i.label FROM matters m "
        "JOIN industries i ON i.code = m.industry_code "
        "WHERE i.label IS NOT NULL ORDER BY i.label"
    ).fetchall()
    return [str(r[0]) for r in rows]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a32, b32 = a.astype(np.float32), b.astype(np.float32)
    denom = np.linalg.norm(a32) * np.linalg.norm(b32)
    return float(np.dot(a32, b32) / denom) if denom else 0.0


def resolve_filter_value(conn: Connection, cache: EmbeddingCache, raw: str) -> Resolution:
    """Resolve free text to an industry label actually present in the corpus, or refuse loudly.

    `cache` is passed in rather than constructed here so a caller with a key can resolve a
    genuinely novel term, and a caller with none still resolves everything already warmed —
    the same content-addressed contract every other retrieval path in this app follows.
    """
    labels = _industry_labels(conn)

    needle = raw.strip().lower()
    exact = next((label for label in labels if label.strip().lower() == needle), None)
    if exact is not None:
        result = Resolution(
            raw=raw, resolved=exact, method="exact", matter_count=_matter_count(conn, exact)
        )
        log.info("filter_value_resolved", raw=raw, resolved=exact, method="exact", similarity=None)
        return result

    if not labels:
        raise UnresolvedFilterValue(raw, [])

    try:
        raw_vector = cache.embed(raw)
        label_vectors = cache.embed_many(labels)
    except EmbeddingUnavailable:
        # No key and this text was never warmed: cannot rank candidates, so refuse rather than
        # silently falling back to string matching, which would be a third, undocumented tier.
        raise UnresolvedFilterValue(raw, sorted(labels)) from None

    scored = sorted(
        ((label, _cosine(raw_vector, vec)) for label, vec in zip(labels, label_vectors)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    best_label, best_similarity = scored[0]

    if best_similarity < SIMILARITY_FLOOR:
        log.info("filter_value_unresolved", raw=raw, best_similarity=round(best_similarity, 3))
        raise UnresolvedFilterValue(raw, [label for label, _ in scored[:8]])

    result = Resolution(
        raw=raw,
        resolved=best_label,
        method="embedding",
        matter_count=_matter_count(conn, best_label),
        similarity=round(best_similarity, 4),
    )
    log.info(
        "filter_value_resolved",
        raw=raw,
        resolved=best_label,
        method="embedding",
        similarity=result.similarity,
    )
    return result

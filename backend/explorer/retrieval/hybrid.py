"""Hybrid retrieval: BM25 + vector, with both score distributions normalized (#17).

The normalization is the whole correctness story. BM25 scores are unbounded and corpus- and
query-dependent — a rare term can produce a 30 where a common one produces a 4 — while cosine
similarities sit in roughly [0, 1]. Adding them raw is not a weighted blend at all: BM25's
scale swamps the vector term and `alpha` silently stops meaning anything. Both sides are
min-max normalized **per query** before combining, and a test asserts it.

`alpha` is configuration, not a constant: `HYBRID_ALPHA`, overridable per request, so the
ablation can sweep it and the API can expose it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import numpy as np
import psycopg
from rank_bm25 import BM25Okapi

from explorer.api.settings import settings
from explorer.retrieval.embeddings import EmbeddingCache, default_cache

DEFAULT_ALPHA = float(os.getenv("HYBRID_ALPHA", "0.5"))

MATTER_SUMMARY_SQL = """
SELECT m.id,
       concat_ws(' · ',
           m.source_contract_title,
           nullif(concat_ws(' / ', m.target_name, m.acquirer_name), ''),
           f.label,
           to_char(m.signing_date, 'YYYY')
       ) AS summary
FROM matters m
LEFT JOIN folio_concepts f ON f.code = m.folio_industry_code
ORDER BY m.id
"""

TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Scored:
    matter_id: str
    score: float
    vector_score: float
    bm25_score: float


def normalize(scores: np.ndarray) -> np.ndarray:
    """Min-max to [0, 1]. A flat distribution maps to zeros, not to NaN — every document being
    equally (ir)relevant must not poison the blend with division by zero."""
    if scores.size == 0:
        return scores
    low, high = float(scores.min()), float(scores.max())
    if high - low < 1e-12:
        return np.zeros_like(scores, dtype=np.float32)
    return ((scores - low) / (high - low)).astype(np.float32)


class HybridIndex:
    """Rebuildable from Postgres in one query; small enough to hold in memory (152 matters)."""

    def __init__(self, ids: list[str], summaries: list[str], cache: EmbeddingCache | None = None):
        self.ids = ids
        self.summaries = summaries
        self.cache = cache or default_cache()
        self.bm25 = BM25Okapi([tokenize(s) for s in summaries])
        vectors = self.cache.embed_many(summaries)
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        self.matrix = matrix / np.where(norms == 0, 1, norms)

    @classmethod
    def from_postgres(cls, dsn: str | None = None, cache: EmbeddingCache | None = None):
        with psycopg.connect(dsn or settings.database_url) as conn:
            rows = conn.execute(MATTER_SUMMARY_SQL).fetchall()
        return cls([r[0] for r in rows], [r[1] or "" for r in rows], cache=cache)

    def search(self, query: str, alpha: float = DEFAULT_ALPHA, limit: int = 10) -> list[Scored]:
        bm25_raw = np.asarray(self.bm25.get_scores(tokenize(query)), dtype=np.float32)

        query_vector = np.asarray(self.cache.embed(query), dtype=np.float32)
        norm = np.linalg.norm(query_vector)
        vector_raw = self.matrix @ (query_vector / (norm if norm else 1.0))

        # normalize BOTH before combining — see module docstring
        bm25 = normalize(bm25_raw)
        vector = normalize(vector_raw)
        blended = alpha * vector + (1.0 - alpha) * bm25

        order = np.argsort(-blended)[:limit]
        return [
            Scored(
                matter_id=self.ids[i],
                score=float(blended[i]),
                vector_score=float(vector[i]),
                bm25_score=float(bm25[i]),
            )
            for i in order
        ]

"""This corpus's embedding cache: the platform's, pointed at this repo's committed vectors.

`EmbeddingCache` itself moved to `semantic_explorer_base.retrieval.embeddings` unchanged — it
referenced nothing about merger agreements. What is domain-bound is the file (`data/embeddings/
vectors.npz`, committed so a clone with no key gets identical results) and the key.
"""

from __future__ import annotations

from pathlib import Path

from semantic_explorer_base.retrieval.embeddings import (
    BATCH_SIZE,
    EMBED_DIMENSIONS,
    EMBED_DTYPE,
    EMBED_MODEL,
    EmbeddingCache,
    EmbeddingUnavailable,
    content_key,
)

from explorer.api.settings import settings

__all__ = [
    "BATCH_SIZE",
    "CACHE_FILE",
    "EMBED_DIMENSIONS",
    "EMBED_DTYPE",
    "EMBED_MODEL",
    "EmbeddingCache",
    "EmbeddingUnavailable",
    "content_key",
    "default_cache",
]

ROOT = Path(__file__).resolve().parents[3]
CACHE_FILE = ROOT / "data" / "embeddings" / "vectors.npz"

_default: EmbeddingCache | None = None


def default_cache() -> EmbeddingCache:
    """Process-wide cache. Loading the 9.5 MB npz per request would dominate query latency."""
    global _default
    if _default is None:
        _default = EmbeddingCache(path=CACHE_FILE, api_key=settings.openai_api_key)
    return _default

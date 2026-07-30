"""Hybrid retrieval (#17).

The assertion that matters most is that **both score distributions are normalized before
combining**. BM25 scores are unbounded; cosine similarities sit in roughly [0, 1]. Blend them
raw and BM25's scale swamps the vector term, `alpha` stops meaning what it says, and the bug
is invisible — results are still plausibly ordered, just not by the weighting anyone chose.

Everything here runs with `OPENAI_API_KEY` unset.
"""

from __future__ import annotations

import os

import numpy as np
import psycopg
import pytest
from explorer.retrieval.embeddings import EmbeddingCache, content_key
from explorer.retrieval.hybrid import DEFAULT_ALPHA, HybridIndex, normalize, tokenize

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


class TestNormalization:
    def test_maps_to_unit_range(self) -> None:
        out = normalize(np.array([2.0, 4.0, 6.0], dtype=np.float32))
        assert out.min() == 0.0
        assert out.max() == 1.0

    def test_flat_distribution_is_zeros_not_nan(self) -> None:
        """Every document equally (ir)relevant must not poison the blend with 0/0."""
        out = normalize(np.array([3.0, 3.0, 3.0], dtype=np.float32))
        assert not np.isnan(out).any()
        assert (out == 0).all()

    def test_empty_is_safe(self) -> None:
        assert normalize(np.array([], dtype=np.float32)).size == 0


@pytest.fixture
def tiny_index(tmp_path):
    """A three-document index whose vectors are hand-written, so scores are predictable."""
    summaries = [
        "Acme Corp acquired by Beta Industries · Manufacturing Industry · 2021",
        "Gamma Pharma merger · Health Care Industry · 2020",
        "Delta Bank combination · Finance and Insurance Services Industry · 2021",
    ]
    vectors = {
        content_key(summaries[0]): np.array([1.0, 0.0], dtype=np.float16),
        content_key(summaries[1]): np.array([0.0, 1.0], dtype=np.float16),
        content_key(summaries[2]): np.array([1.0, 1.0], dtype=np.float16),
        content_key("pharmaceutical deal"): np.array([0.0, 1.0], dtype=np.float16),
        content_key("Acme Corp"): np.array([1.0, 0.0], dtype=np.float16),
    }
    path = tmp_path / "vectors.npz"
    np.savez_compressed(path, **vectors)
    cache = EmbeddingCache(path=path, api_key=None)
    return HybridIndex(["m1", "m2", "m3"], summaries, cache=cache)


class TestBothSidesAreNormalized:
    def test_reported_component_scores_are_in_unit_range(self, tiny_index) -> None:
        """If either side were raw, one of these would leave [0, 1] — BM25 routinely exceeds 1."""
        for scored in tiny_index.search("Acme Corp", alpha=0.5, limit=3):
            assert 0.0 <= scored.bm25_score <= 1.0
            assert 0.0 <= scored.vector_score <= 1.0
            assert 0.0 <= scored.score <= 1.0

    def test_alpha_actually_shifts_the_ranking(self, tiny_index) -> None:
        """The functional consequence of normalizing: a lexical query the vectors disagree with
        must flip as alpha moves. Without normalization BM25 dominates at every alpha."""
        lexical = tiny_index.search("pharmaceutical deal", alpha=0.0, limit=3)
        semantic = tiny_index.search("pharmaceutical deal", alpha=1.0, limit=3)
        assert lexical[0].matter_id != semantic[0].matter_id
        assert semantic[0].matter_id == "m2", "the vector for this query points at Gamma Pharma"

    def test_alpha_1_is_pure_vector_and_alpha_0_is_pure_bm25(self, tiny_index) -> None:
        vector_only = tiny_index.search("Acme Corp", alpha=1.0, limit=3)
        assert all(s.score == pytest.approx(s.vector_score) for s in vector_only)
        bm25_only = tiny_index.search("Acme Corp", alpha=0.0, limit=3)
        assert all(s.score == pytest.approx(s.bm25_score) for s in bm25_only)


class TestAlphaIsConfiguration:
    def test_default_comes_from_the_environment_not_a_literal(self) -> None:
        assert DEFAULT_ALPHA == float(os.getenv("HYBRID_ALPHA", "0.5"))

    def test_search_accepts_a_per_query_alpha(self, tiny_index) -> None:
        assert tiny_index.search("Acme Corp", alpha=0.25, limit=1)


class TestTokenizer:
    def test_lowercases_and_drops_punctuation(self) -> None:
        assert tokenize("Acme Corp., Inc. · 2021") == ["acme", "corp", "inc", "2021"]


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM matters").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


@pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")
class TestAgainstTheRealCorpus:
    def test_index_builds_from_postgres_with_no_api_key(self) -> None:
        """The no-key gate, end to end: 152 summaries embedded entirely from the cache."""
        index = HybridIndex.from_postgres(DSN, cache=EmbeddingCache(api_key=None))
        assert len(index.ids) == 152
        assert index.matrix.shape == (152, 256)
        assert index.cache.api_calls == 0

    def test_a_known_item_query_returns_its_own_matter_first(self) -> None:
        index = HybridIndex.from_postgres(DSN, cache=EmbeddingCache(api_key=None))
        with psycopg.connect(DSN) as conn:
            matter_id, target, acquirer = conn.execute(
                "SELECT id, target_name, acquirer_name FROM matters "
                "WHERE target_name IS NOT NULL AND acquirer_name IS NOT NULL ORDER BY id LIMIT 1"
            ).fetchone()
        top = index.search(f"{target} acquired by {acquirer}", limit=1)
        assert top[0].matter_id == matter_id

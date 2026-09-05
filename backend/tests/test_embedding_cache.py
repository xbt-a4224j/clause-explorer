"""Content-addressed embedding cache (#16).

The point of this file is the **no-key path**. Retrieval, facets, the rollup and every table
view have to work with `OPENAI_API_KEY` unset, or the app cannot be run by anyone who clones
it. That means embeddings are looked up by content hash from a committed cache, and the three
interesting cases each have a defined behaviour:

| case | behaviour |
|---|---|
| hit | vector returned, no API call, no key needed |
| miss **with** a key | embed once, cache in memory |
| miss **without** a key | `EmbeddingUnavailable` naming the cached-item count — never a silent API call, never a bare 500 |

Every test here runs with no key.
"""

from __future__ import annotations

import numpy as np
import pytest
from explorer.retrieval.embeddings import (
    EmbeddingCache,
    EmbeddingUnavailable,
    content_key,
)

VECTOR = np.arange(8, dtype=np.float16)


@pytest.fixture
def cache(tmp_path):
    path = tmp_path / "vectors.npz"
    np.savez_compressed(path, **{content_key("a fiduciary out"): VECTOR})
    return EmbeddingCache(path=path, api_key=None)


class TestContentAddressing:
    def test_key_is_a_hash_of_the_text(self) -> None:
        assert content_key("abc") == content_key("abc")
        assert content_key("abc") != content_key("abd")

    def test_key_is_stable_across_processes(self) -> None:
        """sha256, not hash() — Python's hash is salted per process, so a cache keyed on it
        would silently miss everything after a restart."""
        assert content_key("a fiduciary out").startswith("sha256_")


class TestHit:
    def test_hit_needs_no_key_and_makes_no_call(self, cache: EmbeddingCache) -> None:
        vector = cache.embed("a fiduciary out")
        assert np.array_equal(vector, VECTOR)
        assert cache.api_calls == 0

    def test_entry_count_is_reported(self, cache: EmbeddingCache) -> None:
        assert cache.entry_count == 1


class TestMissWithoutKey:
    def test_raises_with_an_actionable_message(self, cache: EmbeddingCache) -> None:
        with pytest.raises(EmbeddingUnavailable) as raised:
            cache.embed("a ticking fee")
        message = str(raised.value)
        assert "1 cached" in message  # names the cached-item count, per the AC
        assert "warm_cache" in message  # and the command that fixes it
        assert cache.api_calls == 0, "a miss without a key must never call the API"


class TestMissWithKey:
    def test_embeds_once_and_caches_in_memory(self, tmp_path, monkeypatch) -> None:
        """No network here: the client is stubbed. What is asserted is that a second request
        for the same text does not embed again."""
        path = tmp_path / "vectors.npz"
        np.savez_compressed(path, **{content_key("seed"): VECTOR})
        cache = EmbeddingCache(path=path, api_key="test-key-not-real")

        calls: list[str] = []

        def fake_embed(texts: list[str]) -> list[np.ndarray]:
            calls.extend(texts)
            return [np.ones(8, dtype=np.float16) for _ in texts]

        monkeypatch.setattr(cache, "_embed_uncached", fake_embed)

        first = cache.embed("a ticking fee")
        second = cache.embed("a ticking fee")
        assert np.array_equal(first, second)
        assert calls == ["a ticking fee"], "the second call must come from the in-memory cache"

    def test_memory_cached_vectors_do_not_touch_the_committed_file(
        self, tmp_path, monkeypatch
    ) -> None:
        """Warming the cache is an explicit command. An API-key run must not silently rewrite
        a file that is committed to the repo."""
        path = tmp_path / "vectors.npz"
        np.savez_compressed(path, **{content_key("seed"): VECTOR})
        before = path.read_bytes()
        cache = EmbeddingCache(path=path, api_key="test-key-not-real")
        monkeypatch.setattr(
            cache, "_embed_uncached", lambda texts: [np.ones(8, dtype=np.float16) for _ in texts]
        )
        cache.embed("something new")
        assert path.read_bytes() == before


class TestMissingCacheFile:
    def test_absent_cache_is_empty_not_an_error(self, tmp_path) -> None:
        cache = EmbeddingCache(path=tmp_path / "nope.npz", api_key=None)
        assert cache.entry_count == 0
        with pytest.raises(EmbeddingUnavailable, match="0 cached"):
            cache.embed("anything")

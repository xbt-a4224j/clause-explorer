"""Filter-value resolution (#25) — the nastiest failure mode in the design.

Measure and dimension *names* can be enum-locked with structured output; filter *values*
cannot, because they come from free text. `folio_industry = "Health Care"` when the data holds
"Health Care Industry" returns zero rows that look exactly like "we have no comparable deals" —
a silently wrong answer, indistinguishable from a genuinely thin corpus. The resolution ladder
(exact -> alias -> embedding nearest) exists to make that distinction visible instead.

Runs with `OPENAI_API_KEY` unset — the embedding tier reads the committed cache.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.agent.resolve_filter_value import UnresolvedFilterValue, resolve_filter_value
from explorer.retrieval.embeddings import EmbeddingCache

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")


def _corpus_ready() -> bool:
    try:
        with psycopg.connect(DSN, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM folio_concepts").fetchone()[0] > 0
    except Exception:  # noqa: BLE001 - availability probe
        return False


needs_corpus = pytest.mark.skipif(not _corpus_ready(), reason="corpus not loaded")


@pytest.fixture
def conn():  # type: ignore[no-untyped-def]
    with psycopg.connect(DSN) as c:
        yield c


@pytest.fixture
def cache() -> EmbeddingCache:
    # no api_key: proves the embedding tier runs from the committed cache alone
    return EmbeddingCache()


@needs_corpus
class TestExactHit:
    def test_the_exact_label_resolves_by_the_exact_tier(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        result = resolve_filter_value(conn, cache, "Health Care Industry")
        assert result.resolved == "Health Care Industry"
        assert result.method == "exact"
        assert result.matter_count == 25


@needs_corpus
class TestAliasHit:
    def test_a_known_alias_resolves_by_the_alias_tier(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        aliases = conn.execute("SELECT alias, code FROM folio_aliases LIMIT 1000").fetchall()
        singly_owned = None
        for alias, code in aliases:
            owners = {
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT code FROM folio_aliases WHERE lower(alias) = lower(%s)",
                    (alias,),
                ).fetchall()
            }
            if len(owners) == 1:
                singly_owned = (alias, code)
                break
        if singly_owned is None:
            pytest.skip("no unambiguous alias found to test against")
        alias, code = singly_owned
        result = resolve_filter_value(conn, cache, alias)
        assert result.method == "alias"
        assert result.raw == alias


@needs_corpus
class TestEmbeddingHit:
    def test_a_near_miss_resolves_by_the_embedding_tier(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        """ "healthcare" is neither the exact label ("Health Care Industry") nor a checked-in
        alias — this can only succeed through embedding similarity."""
        result = resolve_filter_value(conn, cache, "healthcare")
        assert result.method == "embedding"
        assert result.resolved == "Health Care Industry"
        assert result.raw == "healthcare"

    def test_result_reports_similarity_alongside_the_match(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        result = resolve_filter_value(conn, cache, "healthcare")
        assert result.similarity is not None
        assert 0.0 <= result.similarity <= 1.0


@needs_corpus
class TestUnresolvable:
    def test_an_unresolvable_value_fails_loudly_with_candidates(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        """Never a silent empty result — the caller gets told exactly what does exist."""
        with pytest.raises(UnresolvedFilterValue) as excinfo:
            resolve_filter_value(conn, cache, "not a real industry at all")
        assert excinfo.value.candidates
        assert all(c.endswith("Industry") for c in excinfo.value.candidates)
        assert "not a real industry at all" in str(excinfo.value)

    def test_the_exception_states_the_raw_value(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(UnresolvedFilterValue) as excinfo:
            resolve_filter_value(conn, cache, "not a real industry at all")
        assert excinfo.value.raw == "not a real industry at all"


@needs_corpus
class TestResponseShape:
    def test_the_result_matches_the_documented_shape(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        result = resolve_filter_value(conn, cache, "healthcare")
        assert result.raw == "healthcare"
        assert result.resolved == "Health Care Industry"
        assert result.method in {"exact", "alias", "embedding"}
        assert result.matter_count == 25

"""Filter-value resolution (#25) — the nastiest failure mode in the design.

Measure and dimension *names* can be enum-locked with structured output; filter *values*
cannot, because they come from free text. `industry = "Health Care"` when the data holds
"Health Care Industry" returns zero rows that look exactly like "we have no comparable deals" —
a silently wrong answer, indistinguishable from a genuinely thin corpus. The resolution ladder
(exact -> embedding nearest) exists to make that distinction visible instead.

The ladder had a third rung, an alias tier reading the ontology's `skos:altLabel`s. #49 removed
the ontology; its test went with it rather than being kept as a test of nothing.

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
            return conn.execute("SELECT count(*) FROM industries").fetchone()[0] > 0
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
        assert result.matter_count == 26


@needs_corpus
class TestTheLadderIsTwoTiers:
    def test_only_exact_and_embedding_are_reachable(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        """#49 removed the alias rung with the ontology that supplied it."""
        assert resolve_filter_value(conn, cache, "Health Care Industry").method == "exact"
        assert resolve_filter_value(conn, cache, "healthcare").method == "embedding"

    def test_the_vocabulary_is_labels_the_corpus_carries_not_the_whole_table(self, conn) -> None:  # type: ignore[no-untyped-def]
        """The crosswalk seeds every industry it can name; only some are carried by a matter.
        Resolving to one nothing is tagged with returns zero rows — the exact failure this
        module exists to prevent — so the closed vocabulary is the narrower set."""
        from explorer.agent.resolve_filter_value import _industry_labels

        labels = _industry_labels(conn)
        seeded = conn.execute("SELECT count(*) FROM industries").fetchone()[0]
        carried = conn.execute(
            "SELECT count(DISTINCT industry_code) FROM matters WHERE industry_code IS NOT NULL"
        ).fetchone()[0]
        assert len(labels) == carried
        assert carried < seeded


@needs_corpus
class TestEmbeddingHit:
    def test_a_near_miss_resolves_by_the_embedding_tier(self, conn, cache) -> None:  # type: ignore[no-untyped-def]
        """ "healthcare" is not the exact label ("Health Care Industry"), so this can only
        succeed through embedding similarity."""
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
        assert result.method in {"exact", "embedding"}
        assert result.matter_count == 26

"""MAUD -> matters + deal_points (#8).

MAUD's expert annotations *are* the product data; nothing here re-extracts anything. The
interesting work is provenance: MAUD's excerpt text is not byte-identical to the contract
file it came from, so the span locator has to earn its offsets. Three known differences,
each covered by a fixture test below:

* the contract files carry `________________` page-break artifacts the excerpts drop
* excerpts end with a `(Page 40)` / `(Pages 9-10)` citation that is not source text
* excerpts are discontinuous — literal `<omitted>` markers join separate provisions

The last one matters most: without splitting on `<omitted>` only 65% of excerpts locate.
"""

from __future__ import annotations

import os
import random
import re

import psycopg
import pytest
from explorer.ingest.maud import SpanLocator, clean_excerpt, upsert_maud
from explorer.ingest.maud_corpus import CONTRACTS_DIR, corpus_available

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

needs_corpus = pytest.mark.skipif(
    not corpus_available(), reason="MAUD corpus not downloaded — run scripts/download_maud.sh"
)

SOURCE = (
    "AGREEMENT AND PLAN OF MERGER\n\n"
    "7.2  Conditions to Obligation of Parent.  The obligations of Parent\n"
    "________________\n"
    "shall be subject to the satisfaction of the following conditions:\n"
    "(a) each representation shall be true and correct in all respects.\n\n"
    "9.1  Termination.  This Agreement may be terminated at any time prior to the\n"
    "Effective Time by mutual written consent of the parties hereto.\n"
)


class TestSpanLocator:
    def test_locates_a_plain_excerpt(self) -> None:
        locator = SpanLocator(SOURCE)
        span = locator.locate(
            "This Agreement may be terminated at any time prior to the Effective Time"
        )
        assert span is not None
        start, end = span
        assert clean_excerpt(SOURCE[start:end]).startswith("This Agreement may be terminated")

    def test_tolerates_page_break_artifacts_in_the_source(self) -> None:
        """`________________` sits inside the passage in the file but not in the excerpt."""
        excerpt = (
            "7.2 Conditions to Obligation of Parent. The obligations of Parent "
            "shall be subject to the satisfaction of the following conditions:"
        )
        span = SpanLocator(SOURCE).locate(excerpt)
        assert span is not None
        assert "________________" in SOURCE[span[0] : span[1]]

    def test_strips_the_page_citation(self) -> None:
        excerpt = "9.1 Termination. This Agreement may be terminated (Pages 40-41)"
        span = SpanLocator(SOURCE).locate(excerpt)
        assert span is not None
        assert "(Pages" not in SOURCE[span[0] : span[1]]

    def test_discontinuous_excerpt_spans_from_first_to_last_segment(self) -> None:
        excerpt = (
            "7.2 Conditions to Obligation of Parent. <omitted> "
            "by mutual written consent of the parties hereto."
        )
        span = SpanLocator(SOURCE).locate(excerpt)
        assert span is not None
        text = SOURCE[span[0] : span[1]]
        assert text.startswith("7.2")
        assert text.rstrip().endswith("hereto.")

    def test_absent_text_returns_none_rather_than_a_guess(self) -> None:
        assert SpanLocator(SOURCE).locate("A ticking fee accrues at 5% per annum monthly") is None


@needs_corpus
class TestParse:
    @pytest.fixture(scope="class")
    def parsed(self, maud_parsed):
        return maud_parsed

    def test_152_matters(self, parsed) -> None:
        matters, _ = parsed
        assert len(matters) == 152

    def test_matters_carry_their_source_file(self, parsed) -> None:
        matters, _ = parsed
        assert all(m.source_file.endswith(".txt") for m in matters)
        assert all((CONTRACTS_DIR / os.path.basename(m.source_file)).exists() for m in matters)

    def test_deal_points_are_long_and_unique_per_matter(self, parsed) -> None:
        _, points = parsed
        keys = [(p.matter_id, p.deal_point_name) for p in points]
        assert len(keys) == len(set(keys))

    def test_92_deal_point_names_read_from_the_corpus(self, parsed) -> None:
        _, points = parsed
        assert len({p.deal_point_name for p in points}) == 92

    def test_everything_from_maud_is_gold_not_inferred(self, parsed) -> None:
        _, points = parsed
        assert not any(p.is_inferred for p in points)

    def test_positions_are_the_expert_answers(self, parsed) -> None:
        _, points = parsed
        assert all(p.position.strip() for p in points)

    def test_unlocatable_spans_are_null_not_fabricated(self, parsed) -> None:
        _, points = parsed
        for p in points:
            assert (p.source_span_start is None) == (p.source_span_end is None)
            if p.source_span_start is not None:
                assert p.source_span_end > p.source_span_start


@needs_corpus
class TestProvenance:
    """The AC: a stored span must be traceable to a byte range in the downloaded file."""

    @pytest.fixture(scope="class")
    def parsed(self, maud_parsed):
        return maud_parsed

    def test_sampled_spans_contain_their_labelled_text(self, parsed) -> None:
        _, points = parsed
        located = [p for p in points if p.source_span_start is not None]
        random.seed(8)
        sample = random.sample(located, 20)
        sources: dict[str, str] = {}
        for point in sample:
            text = sources.setdefault(
                point.matter_id,
                (CONTRACTS_DIR / f"{point.matter_id}.txt").read_text(
                    encoding="utf-8", errors="replace"
                ),
            )
            span = clean_excerpt(text[point.source_span_start : point.source_span_end])
            head = clean_excerpt(re.split(r"<omitted>", point.source_excerpt)[0])[:60]
            assert head in span, f"{point.matter_id}/{point.deal_point_name}: span lost its text"


@pytest.mark.skipif(not corpus_available(), reason="MAUD corpus not downloaded")
class TestLoad:
    @pytest.fixture(scope="class")
    def loaded(self, maud_parsed):
        matters, points = maud_parsed
        with psycopg.connect(DSN) as conn:
            upsert_maud(conn, matters, points)
        return matters, points

    def test_row_counts_match_what_was_parsed(self, loaded) -> None:
        matters, points = loaded
        with psycopg.connect(DSN) as conn:
            assert conn.execute("SELECT count(*) FROM matters").fetchone()[0] == len(matters)
            assert conn.execute("SELECT count(*) FROM deal_points").fetchone()[0] == len(points)

    def test_idempotent(self, loaded) -> None:
        matters, points = loaded
        with psycopg.connect(DSN) as conn:
            before = conn.execute("SELECT count(*) FROM deal_points").fetchone()[0]
            upsert_maud(conn, matters, points)
            after = conn.execute("SELECT count(*) FROM deal_points").fetchone()[0]
        assert after == before

    def test_deal_point_names_are_rows_not_columns(self, loaded) -> None:
        """The LONG-shape invariant, asserted against loaded data rather than the schema."""
        with psycopg.connect(DSN) as conn:
            names = conn.execute(
                "SELECT count(DISTINCT deal_point_name) FROM deal_points"
            ).fetchone()[0]
        assert names == 92

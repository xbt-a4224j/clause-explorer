"""Anchoring MAUD's quoted answer text inside the recorded span (#43).

A recorded span says *where in the agreement the answer was found*: for a discontinuous
annotation it is the envelope from the first quoted provision to the last, which over this
corpus reaches a 90th percentile of 238,949 characters. The annotation also carries the
quoted text itself, so where that text sits contiguously and **exactly once** inside the
recorded span, the span can be replaced by the characters the annotator actually quoted.

The uniqueness rule is the whole point. Two occurrences means we do not know which one the
annotator meant, and storing the first would be a wrong offset that opens a real-looking
clause — the failure mode CLAUDE.md exists to prevent. Ambiguous is a miss.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from explorer.ingest.maud import (
    DealPoint,
    Matter,
    SpanLocator,
    _strip_rules,
    clean_excerpt,
    upsert_maud,
)
from explorer.ingest.maud_corpus import corpus_available

DSN = os.getenv("CLAUSE_EXPLORER_DB", "postgresql://explorer:explorer@localhost:5432/explorer")

CLAUSE = (
    "9.1  Termination.  This Agreement may be terminated at any time prior to the "
    "Effective Time by mutual written consent of the parties hereto."
)
REPEATED = (
    "Each party shall use its reasonable best efforts to consummate the transactions "
    "contemplated by this Agreement."
)

SOURCE = (
    "AGREEMENT AND PLAN OF MERGER\n\n"
    "7.2  Conditions to Obligation of Parent.  The obligations of Parent\n"
    "________________\n"
    "shall be subject to the satisfaction of the following conditions:\n"
    "(a) each representation shall be true and correct in all respects.\n\n"
    f"{REPEATED}\n\n"
    f"{CLAUSE}\n\n"
    "10.4  Amendment.  This Agreement may be amended by the parties.\n\n"
    f"{REPEATED}\n"
)
WHOLE = (0, len(SOURCE))


class TestAnchorInsideASpan:
    def test_an_excerpt_that_appears_once_anchors_to_its_own_characters(self) -> None:
        span = SpanLocator(SOURCE).anchor(CLAUSE, WHOLE)
        assert span is not None
        assert SOURCE[span[0] : span[1]] == CLAUSE
        assert span[1] - span[0] < len(SOURCE)

    def test_an_excerpt_that_appears_twice_does_not_anchor(self) -> None:
        """Ambiguous is a miss. The first occurrence would be a guess wearing an offset."""
        assert SpanLocator(SOURCE).anchor(REPEATED, WHOLE) is None

    def test_an_excerpt_that_does_not_appear_does_not_anchor(self) -> None:
        assert SpanLocator(SOURCE).anchor("A ticking fee accrues at 5% per annum", WHOLE) is None

    def test_only_occurrences_inside_the_recorded_span_count(self) -> None:
        """The second copy of REPEATED is outside this window, so the first is unambiguous."""
        end = SOURCE.index(CLAUSE)
        span = SpanLocator(SOURCE).anchor(REPEATED, (0, end))
        assert span is not None
        assert SOURCE[span[0] : span[1]] == REPEATED

    def test_an_occurrence_outside_the_recorded_span_is_not_reachable(self) -> None:
        start = SOURCE.index(CLAUSE)
        assert SpanLocator(SOURCE).anchor(REPEATED, (start, len(SOURCE) - 40)) is None

    def test_a_page_rule_inside_the_passage_does_not_block_the_anchor(self) -> None:
        """`________________` is a page-break rule in the file and absent from the excerpt."""
        excerpt = (
            "7.2 Conditions to Obligation of Parent. The obligations of Parent "
            "shall be subject to the satisfaction of the following conditions:"
        )
        span = SpanLocator(SOURCE).anchor(excerpt, WHOLE)
        assert span is not None
        # The rule is inside the quoted passage, so the byte range necessarily contains it;
        # what must hold is that the span carries the quotation and nothing else.
        assert "________________" in SOURCE[span[0] : span[1]]
        assert _strip_rules(clean_excerpt(SOURCE[span[0] : span[1]])) == excerpt

    def test_the_page_citation_is_not_treated_as_contract_text(self) -> None:
        span = SpanLocator(SOURCE).anchor(f"{CLAUSE} (Pages 40-41)", WHOLE)
        assert span is not None
        assert SOURCE[span[0] : span[1]] == CLAUSE

    def test_a_discontinuous_excerpt_does_not_anchor(self) -> None:
        """Two quoted provisions are not one clause; the envelope stays `recorded`."""
        excerpt = f"7.2 Conditions to Obligation of Parent. <omitted> {CLAUSE}"
        assert SpanLocator(SOURCE).anchor(excerpt, WHOLE) is None

    def test_a_short_omitted_piece_still_blocks_the_anchor(self) -> None:
        """`9.1 Termination.` is below the segment floor `locate` uses, but it is quoted text.

        Dropping it as noise would anchor to the surviving provision alone while the stored
        span claims to be the whole quotation — 18 corpus rows anchored wrongly that way.
        """
        excerpt = f"9.1 Termination. <omitted> {CLAUSE[len('9.1  Termination.  ') :]}"
        assert SpanLocator(SOURCE).anchor(excerpt, WHOLE) is None

    def test_a_span_that_is_none_searches_the_whole_document(self) -> None:
        span = SpanLocator(SOURCE).anchor(CLAUSE, None)
        assert span is not None
        assert SOURCE[span[0] : span[1]] == CLAUSE

    def test_locate_is_unchanged_by_anchoring(self) -> None:
        """Recorded spans keep their old semantics; anchoring is a separate, stricter pass."""
        excerpt = "7.2 Conditions to Obligation of Parent. <omitted> 9.1 Termination."
        recorded = SpanLocator(SOURCE).locate(excerpt)
        assert recorded is not None
        assert SOURCE[recorded[0] : recorded[1]].startswith("7.2")


@pytest.mark.skipif(not corpus_available(), reason="MAUD corpus not downloaded")
class TestParsedSpanKind:
    @pytest.fixture(scope="class")
    def points(self, maud_parsed):
        return maud_parsed[1]

    def test_span_kind_is_recorded_anchored_or_null(self, points) -> None:
        assert {p.span_kind for p in points} <= {"anchored", "recorded", None}

    def test_span_kind_is_null_exactly_when_there_is_no_span(self, points) -> None:
        for p in points:
            assert (p.span_kind is None) == (p.source_span_start is None)

    def test_an_anchored_span_is_the_quoted_text_itself(self, points) -> None:
        """Not merely narrower — the characters at the span clean to the excerpt exactly."""
        from explorer.ingest.maud_corpus import CONTRACTS_DIR

        anchored = [p for p in points if p.span_kind == "anchored"]
        assert anchored, "no rows anchored at all"
        sources: dict[str, str] = {}
        for point in anchored:
            text = sources.setdefault(
                point.matter_id,
                (CONTRACTS_DIR / f"{point.matter_id}.txt").read_text(
                    encoding="utf-8", errors="replace"
                ),
            )
            span_text = _strip_rules(
                clean_excerpt(text[point.source_span_start : point.source_span_end])
            )
            assert span_text == _strip_rules(clean_excerpt(point.source_excerpt))


@pytest.mark.skipif(not corpus_available(), reason="MAUD corpus not downloaded")
class TestSpanKindPersists:
    def test_span_kind_round_trips_through_the_upsert(self) -> None:
        try:
            conn = psycopg.connect(DSN, connect_timeout=2)
        except Exception:  # noqa: BLE001 - availability probe; any failure means skip
            pytest.skip("Postgres not reachable")
        matter = Matter(id="test_matter_43", source_file="x.txt", source_contract_title="t")
        point = DealPoint(
            matter_id="test_matter_43",
            deal_point_name="Test Deal Point 43",
            position="present",
            source_span_start=10,
            source_span_end=20,
            source_excerpt="irrelevant",
            span_kind="anchored",
        )
        with conn:
            upsert_maud(conn, [matter], [point])
            stored = conn.execute(
                "SELECT span_kind FROM deal_points WHERE matter_id = %s", (matter.id,)
            ).fetchone()
            assert stored is not None and stored[0] == "anchored"
            conn.execute("DELETE FROM matters WHERE id = %s", (matter.id,))
            conn.commit()

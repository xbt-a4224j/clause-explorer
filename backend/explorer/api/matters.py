"""`GET /matters/{id}` — the matter card and its drill-through (#20).

The card is the unit a partner actually consumes, so the discipline that matters here is
provenance: every deal point carries the byte range it came from, and the clause text is the
**exact slice** of the downloaded source file at those offsets. Nothing is paraphrased, nothing
is re-extracted, and a span that cannot be resolved returns `clause_text: null` with a reason
rather than a plausible-looking excerpt (CLAUDE.md: a row whose text cannot be traced to a byte
range in the source is a bug).

The corpus is gitignored, so text can be legitimately absent on a fresh checkout. That is
reported per deal point, never faked and never silently blank.

This does not go through Cube. Cube's footprint is facet counts and rollups; individual record
fetch is explicitly outside it.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from explorer.api.logging import get_logger
from explorer.api.settings import settings

router = APIRouter()
log = get_logger()

# Why a cache: a matter's deal points all cite the same file, so a 92-row card would otherwise
# read the same ~700 KB contract 92 times. Keyed by path, cleared per request set by size.
_TEXT_CACHE: dict[str, str] = {}
_TEXT_CACHE_MAX = 8

# Corpora live under data/; `matters.source_file` is recorded relative to it.
DATA_ROOT = (Path(__file__).resolve().parents[3] / "data").resolve()

NO_SPAN = "MAUD located no character range for this label in the source agreement."
NO_FILE = "The source agreement is not on disk — the corpus is gitignored (see docs/provenance.md)."
BAD_SPAN = "The recorded character range falls outside the source agreement."


class DealPointDetail(BaseModel):
    deal_point_name: str
    position: str
    is_inferred: bool
    numeric_value: float | None
    source_span_start: int | None
    source_span_end: int | None
    clause_text: str | None = Field(
        default=None,
        description="The exact characters at [start, end) in the source file. Never generated.",
    )
    text_unavailable: str | None = Field(
        default=None,
        description="Why there is no clause text. Set whenever clause_text is null.",
    )


class MatterDetail(BaseModel):
    matter_id: str
    target_name: str | None
    acquirer_name: str | None
    industry: str | None
    is_inferred_industry: bool
    signing_date: str | None
    deal_value_usd: float | None
    source_file: str | None
    source_contract_title: str | None
    deal_point_count: int
    located_count: int
    deal_points: list[DealPointDetail]
    summary: str


def _read_source(source_file: str | None) -> str | None:
    """The downloaded contract, or None if it is not on disk."""
    if not source_file:
        return None
    if source_file in _TEXT_CACHE:
        return _TEXT_CACHE[source_file]

    # `source_file` is recorded relative to `data/` at ingest (e.g.
    # "maud/data/contracts/contract_1.txt"), so it resolves against DATA_ROOT, not the repo root.
    path = (DATA_ROOT / source_file).resolve()
    # A stored path must not escape the corpus directory. It comes from our own ingest rather
    # than a request, but this is the one place a DB value becomes a filesystem read.
    if not path.is_relative_to(DATA_ROOT) or not path.is_file():
        return None

    text = path.read_text(encoding="utf-8", errors="replace")
    if len(_TEXT_CACHE) >= _TEXT_CACHE_MAX:
        _TEXT_CACHE.clear()
    _TEXT_CACHE[source_file] = text
    return text


class SourceSlice(NamedTuple):
    """What a recorded span actually yields.

    `text` and `unavailable` remain mutually exclusive. `span_chars` and `is_excerpt` carry the
    thing the old two-tuple could not say: the span exists and was read, but it is too wide to
    be the operative language, so what is shown is a bounded excerpt of it.
    """

    text: str | None
    unavailable: str | None
    span_chars: int | None = None
    is_excerpt: bool = False


def _slice(text: str | None, start: int | None, end: int | None) -> SourceSlice:
    """The characters at a recorded span, bounded when the span is document-scale."""
    if start is None or end is None:
        return SourceSlice(None, NO_SPAN)
    if text is None:
        return SourceSlice(None, NO_FILE)
    if start < 0 or end > len(text) or end <= start:
        return SourceSlice(None, BAD_SPAN)

    span_chars = end - start
    if span_chars > settings.max_clause_chars:
        # A span this wide is where the answer was found, not the language that carries it.
        return SourceSlice(
            text[start : start + settings.excerpt_chars], None, span_chars, is_excerpt=True
        )
    return SourceSlice(text[start:end], None, span_chars, is_excerpt=False)


def slice_source(source_file: str | None, start: int | None, end: int | None) -> SourceSlice:
    """The clause at a byte range, or None with the reason.

    The single entry point for turning a recorded span into text, shared by the matter card
    (#20) and the deal-terms drill-through (#21). Two implementations would eventually disagree
    about what "no text" means, and that disagreement is invisible in the UI.
    """
    return _slice(_read_source(source_file), start, end)


def _summary(matter: MatterDetail, top: list[DealPointDetail]) -> str:
    """A paragraph a partner pastes into a deck.

    It leaves the app, so everything the UI conveys with styling has to survive as words: the
    inferred flag becomes the literal word, and the denominator is written out. No percentage
    is computed here — this is one matter, and `6 of 8` reasoning belongs to the rollup (#21).
    """
    parties = matter.target_name or matter.matter_id
    if matter.acquirer_name:
        parties = f"{matter.acquirer_name} / {parties}"

    industry = matter.industry or "industry not classified"
    if matter.industry and matter.is_inferred_industry:
        industry = f"{industry} (inferred from SIC, not an expert label)"

    signed = f", signed {matter.signing_date}" if matter.signing_date else ""
    value = (
        "deal value not available"
        if matter.deal_value_usd is None
        else f"${matter.deal_value_usd:,.0f}"
    )

    terms = (
        "; ".join(f"{dp.deal_point_name}: {dp.position}" for dp in top) or "no deal points recorded"
    )

    return (
        f"{parties} — {industry}{signed}. {value}. "
        f"Negotiated terms (n={matter.deal_point_count}, {matter.located_count} traced to a "
        f"source span): {terms}. "
        f"Source: {matter.source_contract_title or matter.matter_id} "
        f"({matter.source_file or 'file not recorded'}). "
        f"Deal-point labels are MAUD expert annotations (CC BY 4.0)."
    )


# How many terms the pasted paragraph names. The full set is on the card; a paragraph listing
# 92 deal points is not a paragraph.
SUMMARY_TERMS = 5


@router.get("/matters/{matter_id}", response_model=MatterDetail)
def matter_detail(matter_id: str) -> MatterDetail:
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            """
            SELECT m.id, m.target_name, m.acquirer_name, f.label, m.is_inferred_industry,
                   m.signing_date, m.deal_value_usd, m.source_file, m.source_contract_title
              FROM matters m
              LEFT JOIN folio_concepts f ON f.code = m.folio_industry_code
             WHERE m.id = %(id)s
            """,
            {"id": matter_id},
        ).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"No matter {matter_id!r}. This is not an empty result — the id does not exist.",
            )

        dp_rows = conn.execute(
            """
            SELECT deal_point_name, position, is_inferred, numeric_value,
                   source_span_start, source_span_end
              FROM deal_points
             WHERE matter_id = %(id)s
             ORDER BY deal_point_name
            """,
            {"id": matter_id},
        ).fetchall()

    source_file = row[7]
    text = _read_source(source_file)

    deal_points: list[DealPointDetail] = []
    for name, position, is_inferred, numeric_value, start, end in dp_rows:
        sliced = _slice(text, start, end)
        clause_text, unavailable = sliced.text, sliced.unavailable
        deal_points.append(
            DealPointDetail(
                deal_point_name=name,
                position=position,
                is_inferred=is_inferred,
                numeric_value=float(numeric_value) if numeric_value is not None else None,
                source_span_start=start,
                source_span_end=end,
                clause_text=clause_text,
                text_unavailable=unavailable,
            )
        )

    detail = MatterDetail(
        matter_id=row[0],
        target_name=row[1],
        acquirer_name=row[2],
        industry=row[3],
        is_inferred_industry=row[4],
        signing_date=row[5].isoformat() if row[5] else None,
        deal_value_usd=float(row[6]) if row[6] is not None else None,
        source_file=source_file,
        source_contract_title=row[8],
        deal_point_count=len(deal_points),
        located_count=sum(1 for dp in deal_points if dp.source_span_start is not None),
        deal_points=deal_points,
        summary="",
    )
    detail.summary = _summary(detail, deal_points[:SUMMARY_TERMS])

    log.info(
        "matter_detail",
        matter_id=matter_id,
        deal_point_count=detail.deal_point_count,
        located_count=detail.located_count,
        source_text_available=text is not None,
    )
    return detail

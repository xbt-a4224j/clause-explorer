"""Parse MAUD's expert annotations into `matters` and LONG `deal_points` (#8).

**The labels are the product data.** Nothing here extracts anything from contract text —
MAUD's annotators are transactional lawyers and their answers are gold. Running our own
extractor over this corpus is a separate, explicitly-labelled calibration experiment (#28);
mixing the two would destroy the only ground truth we have.

Shape of the source: each CSV row is (contract, question, answer, text). `question` is the
deal point — 92 of them, the ABA list — and `answer` is the negotiated position. `label` is
merely the answer's index within its answer set; reading it as the deal point yields 10
values instead of 92 and looks entirely plausible.

Only `data_type == 'main'` rows are loaded. `abridged` is the same annotation over a shortened
passage and `rare_answers` is a training aid keyed to a `<RARE_ANSWERS>` pseudo-contract;
loading either would double-count matters in every rollup.
"""

from __future__ import annotations

import bisect
import csv
import re
import time
from dataclasses import dataclass
from functools import cached_property

import psycopg
from psycopg import Connection

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.ingest.maud_corpus import (
    contract_paths,
    label_csv_paths,
    require_corpus,
)

WHITESPACE = re.compile(r"\s+")
# trailing (or embedded) citation MAUD appends to an excerpt; not contract text
PAGE_CITATION = re.compile(r"\(Pages?\s*[\d\s,\-–]+\)")
OMITTED = re.compile(r"<omitted>")
RARE_ANSWERS = "<RARE_ANSWERS>"

# anchor lengths tried longest-first when locating a segment; long anchors are unambiguous,
# short ones are the fallback for segments that differ from the source in the middle
ANCHOR_LENGTHS = (400, 200, 100, 50, 30, 20)
MIN_SEGMENT = 20

# A run of underscores, dashes or dots on its own is a page-break rule or a leader line — a
# typographic artifact of the filing, not language. MAUD's excerpts drop them, the contract
# files keep them, and until they are dropped on our side too an otherwise exact quotation
# fails to match: dropping them moves the measured anchor rate from 32.3% to 57.8%
# (docs/results/span-anchoring.md). Deleting a rule cannot change what the text says.
RULE_TOKEN = re.compile(r"^[_\-–—=.*]{3,}$")

ANCHORED = "anchored"
RECORDED = "recorded"

# why an anchoring attempt ended the way it did; ANCHORED is the only success
DISCONTINUOUS = "discontinuous excerpt"
TOO_SHORT = "excerpt too short to anchor"
NOT_FOUND = "quoted text not found in the span"
AMBIGUOUS = "quoted text appears more than once in the span"
ANCHOR_OUTCOMES = (ANCHORED, DISCONTINUOUS, TOO_SHORT, NOT_FOUND, AMBIGUOUS)


def clean_excerpt(text: str) -> str:
    """Collapse whitespace and drop page citations. The comparison form for both sides."""
    return WHITESPACE.sub(" ", PAGE_CITATION.sub(" ", text)).strip()


class SpanLocator:
    """Map a MAUD excerpt back to a byte range in the contract file it came from.

    The excerpt is never byte-identical to the source: the file carries page-break rules the
    excerpt drops, the excerpt carries a page citation the file does not have, and multiple
    provisions are joined with `<omitted>`. So each `<omitted>`-separated segment is anchored
    independently by its head and tail, and the stored span runs from the first segment's
    start to the last segment's end.

    For a discontinuous excerpt that range therefore *contains* material the annotator did
    not quote. That is the accepted cost: the alternative is storing no span at all for 38%
    of rows, and a drill-through that lands on the right provisions with some surrounding
    text beats one that cannot open. Never guessed — a segment that will not anchor returns
    None and the row stores NULL (`no fabricated numbers` applies to offsets too).
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self._normalized, self._offsets = _normalize_with_offsets(source)

    def locate(self, excerpt: str) -> tuple[int, int] | None:
        segments = [
            s for s in (clean_excerpt(p) for p in OMITTED.split(excerpt)) if len(s) >= MIN_SEGMENT
        ]
        if not segments:
            return None

        spans: list[tuple[int, int]] = []
        cursor = 0
        for segment in segments:
            found = self._find(segment, cursor)
            if found is None:
                return None
            spans.append(found)
            cursor = found[1]

        start_norm = min(s for s, _ in spans)
        end_norm = max(e for _, e in spans)
        start = self._offsets[start_norm]
        end = (
            self._offsets[end_norm - 1] + 1
            if end_norm - 1 < len(self._offsets)
            else len(self.source)
        )
        return start, end

    @cached_property
    def _anchor_index(self) -> tuple[str, list[int]]:
        """A second normalized view, with typographic rules deleted, used only by `anchor`.

        Kept separate from the index `locate` uses so that recorded spans keep exactly the
        semantics they had before #43 — anchoring is a stricter pass layered on top, never a
        change to what "recorded" means.
        """
        return _normalize_with_offsets(self.source, drop_rules=True)

    def anchor(self, excerpt: str, span: tuple[int, int] | None) -> tuple[int, int] | None:
        """The anchored span, or None. `anchor_with_reason` carries why a miss missed."""
        return self.anchor_with_reason(excerpt, span)[0]

    def anchor_with_reason(
        self, excerpt: str, span: tuple[int, int] | None
    ) -> tuple[tuple[int, int] | None, str]:
        """The characters the annotator actually quoted, if they sit uniquely inside `span`.

        `span` is the recorded span, or None to search the whole document (the 495 deal points
        MAUD's excerpt would not locate at all). Returns None — a miss, never a guess — when:

        * the excerpt is discontinuous (`<omitted>` joins separate provisions): several
          provisions are not one clause, and storing one of them would present part of the
          basis for the answer as the whole of it;
        * the quoted text is not present in the window verbatim after whitespace collapse and
          rule deletion (the filing's own page furniture is inside some quotations);
        * **the quoted text appears more than once in the window.** Then we do not know which
          occurrence the annotator meant. Taking the first would store an offset that opens a
          real clause, looks entirely correct, and is wrong.

        The second element is the outcome, one of ANCHOR_OUTCOMES, so the hit-rate report
        can say *why* a miss missed without a second copy of this logic.
        """
        # Any non-empty piece counts, unlike `locate`'s MIN_SEGMENT floor: an annotation
        # reading `9.8 Remedies. <omitted> (b) Specific Performance. ...` has a first piece of
        # 13 characters, and dropping it as noise would anchor the span to the second
        # provision while claiming the span is the whole quotation. Measured: 18 rows anchored
        # wrongly in exactly that way before this rule (7,494 anchors then, 7,476 now).
        pieces = [s for s in (clean_excerpt(p) for p in OMITTED.split(excerpt)) if s]
        if len(pieces) != 1:
            return None, DISCONTINUOUS
        needle = _strip_rules(pieces[0])
        if len(needle) < MIN_SEGMENT:
            return None, TOO_SHORT

        normalized, offsets = self._anchor_index
        low, high = 0, len(offsets)
        if span is not None:
            low = bisect.bisect_left(offsets, span[0])
            high = bisect.bisect_left(offsets, span[1])

        at = normalized.find(needle, low, high)
        if at == -1:
            return None, NOT_FOUND
        if normalized.find(needle, at + 1, high) != -1:
            return None, AMBIGUOUS
        return (offsets[at], offsets[at + len(needle) - 1] + 1), ANCHORED

    def _find(self, segment: str, cursor: int) -> tuple[int, int] | None:
        for length in ANCHOR_LENGTHS:
            if length > len(segment):
                continue
            head = segment[:length]
            start = self._normalized.find(head, cursor)
            if start == -1:
                # segments are usually in document order, but not always; fall back to a
                # whole-document search before giving up
                start = self._normalized.find(head)
            if start == -1:
                continue
            for tail_length in ANCHOR_LENGTHS:
                if tail_length > len(segment):
                    continue
                tail = segment[-tail_length:]
                end = self._normalized.find(tail, start)
                if end != -1:
                    return start, end + tail_length
            return start, start + len(segment)
        return None


TOKEN = re.compile(r"\S+")


def _strip_rules(text: str) -> str:
    """The same whitespace-collapsed form the anchor index uses, for the excerpt side."""
    return " ".join(token for token in text.split(" ") if not RULE_TOKEN.match(token))


def _normalize_with_offsets(source: str, drop_rules: bool = False) -> tuple[str, list[int]]:
    """Whitespace-collapsed text plus, per normalized character, its offset in `source`.

    Built token-wise rather than character-wise on purpose: the per-character version is the
    obvious way to write this and made a full corpus parse take minutes — 152 contracts of
    ~350 KB each is 53 million Python loop iterations. `finditer` + `extend(range(...))`
    pushes the same work into C and takes seconds.
    """
    chars: list[str] = []
    offsets: list[int] = []
    for match in TOKEN.finditer(source):
        token = match.group()
        if drop_rules and RULE_TOKEN.match(token):
            continue
        start = match.start()
        if chars:
            chars.append(" ")
            offsets.append(start - 1)
        chars.append(token)
        offsets.extend(range(start, match.end()))
    return "".join(chars), offsets


# MAUD records durations and percentages as answer text: "4 business days", "within 12
# months", "50%". The number is part of the expert's own label, so reading it is normalisation
# — nothing here looks at contract text. A position that only bounds a value ("Greater than 5
# business days") yields None: storing 5 would turn an inequality into a data point, and it
# would sit in a median looking exactly like a measured 5.
LEADING_NUMBER = re.compile(
    r"^(?:within|approximately|about)?\s*(\d+(?:\.\d+)?)\s*(?:%|[a-z])", re.IGNORECASE
)
BOUND_WORDS = ("greater than", "less than", "more than", "fewer than", "at least", "at most")


def numeric_from_position(position: str) -> float | None:
    """The number an expert recorded in this answer, or None if the answer is not a value."""
    text = position.strip().lower()
    if not text or any(text.startswith(word) for word in BOUND_WORDS):
        return None
    match = LEADING_NUMBER.match(text)
    return float(match.group(1)) if match else None


@dataclass(frozen=True)
class Matter:
    id: str
    source_file: str
    source_contract_title: str
    corpus: str = "maud"


@dataclass(frozen=True)
class DealPoint:
    matter_id: str
    deal_point_name: str
    position: str
    source_span_start: int | None
    source_span_end: int | None
    source_excerpt: str
    numeric_value: float | None = None
    is_inferred: bool = False
    # 'anchored' — the span is the quoted answer text itself, located uniquely (#43).
    # 'recorded' — the span is MAUD's own envelope: where the answer was found, which for a
    # discontinuous annotation includes provisions the annotator did not quote.
    # None — no span at all; nothing to say about a range that does not exist.
    span_kind: str | None = None


TITLE_LIMIT = 200


def _title_from(source: str) -> str:
    """The document's own opening line-run, trimmed. Real bytes from the file — party names
    and dates come from EDGAR in #9 rather than being guessed at here."""
    head = clean_excerpt(source[:600]).lstrip("﻿")
    return head[:TITLE_LIMIT].strip() or "untitled"


def parse_maud() -> tuple[list[Matter], list[DealPoint]]:
    require_corpus()

    sources: dict[str, str] = {}
    matters: list[Matter] = []
    for path in contract_paths():
        text = path.read_text(encoding="utf-8", errors="replace")
        sources[path.stem] = text
        matters.append(
            Matter(
                id=path.stem,
                source_file=str(path.relative_to(path.parents[3])),
                source_contract_title=_title_from(text),
            )
        )

    # one row per (matter, deal point); the first `main` row wins, and MAUD has exactly one
    # answer per pair (verified: 12,937 pairs, all with a single distinct answer)
    annotations: dict[tuple[str, str], tuple[str, str]] = {}
    for csv_path in label_csv_paths():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["data_type"] != "main" or row["contract_name"] == RARE_ANSWERS:
                    continue
                key = (row["contract_name"], row["question"])
                if key in annotations:
                    continue
                annotations[key] = (row["answer"], row["text"])

    locators: dict[str, SpanLocator] = {}
    points: list[DealPoint] = []
    for (matter_id, deal_point_name), (answer, excerpt) in sorted(annotations.items()):
        if matter_id not in sources:
            continue  # labelled contract whose text is not in the corpus; drop, never invent
        # NOT setdefault: its default argument is evaluated on every call, so it would
        # rebuild the normalized index once per deal point (12,937 times) instead of once
        # per matter (152). Same result, ~60x the runtime.
        if matter_id not in locators:
            locators[matter_id] = SpanLocator(sources[matter_id])
        locator = locators[matter_id]
        recorded = locator.locate(excerpt)
        # The recorded span says where the answer was found; try to replace it with the text
        # the annotator quoted, searched inside it (or in the whole document when MAUD's
        # excerpt located nothing at all). A miss keeps the recorded span untouched.
        anchored = locator.anchor(excerpt, recorded)
        span = anchored or recorded
        points.append(
            DealPoint(
                matter_id=matter_id,
                deal_point_name=deal_point_name,
                position=answer,
                numeric_value=numeric_from_position(answer),
                source_span_start=span[0] if span else None,
                source_span_end=span[1] if span else None,
                source_excerpt=excerpt,
                is_inferred=False,
                span_kind=(ANCHORED if anchored else RECORDED) if span else None,
            )
        )
    return matters, points


UPSERT_MATTER = """
INSERT INTO matters (id, source_file, source_contract_title, corpus)
VALUES (%s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    source_file = EXCLUDED.source_file,
    source_contract_title = EXCLUDED.source_contract_title,
    corpus = EXCLUDED.corpus
WHERE (matters.source_file, matters.source_contract_title, matters.corpus)
  IS DISTINCT FROM (EXCLUDED.source_file, EXCLUDED.source_contract_title, EXCLUDED.corpus)
"""

UPSERT_DEAL_POINT = """
INSERT INTO deal_points
    (matter_id, deal_point_name, position, numeric_value, source_span_start, source_span_end,
     span_kind, is_inferred)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (matter_id, deal_point_name) DO UPDATE SET
    position = EXCLUDED.position,
    numeric_value = EXCLUDED.numeric_value,
    source_span_start = EXCLUDED.source_span_start,
    source_span_end = EXCLUDED.source_span_end,
    span_kind = EXCLUDED.span_kind,
    is_inferred = EXCLUDED.is_inferred
WHERE (deal_points.position, deal_points.numeric_value, deal_points.source_span_start,
       deal_points.source_span_end, deal_points.span_kind, deal_points.is_inferred)
  IS DISTINCT FROM
      (EXCLUDED.position, EXCLUDED.numeric_value, EXCLUDED.source_span_start,
       EXCLUDED.source_span_end, EXCLUDED.span_kind, EXCLUDED.is_inferred)
"""


def upsert_maud(conn: Connection, matters: list[Matter], points: list[DealPoint]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            UPSERT_MATTER,
            [(m.id, m.source_file, m.source_contract_title, m.corpus) for m in matters],
        )
        cur.executemany(
            UPSERT_DEAL_POINT,
            [
                (
                    p.matter_id,
                    p.deal_point_name,
                    p.position,
                    p.numeric_value,
                    p.source_span_start,
                    p.source_span_end,
                    p.span_kind,
                    p.is_inferred,
                )
                for p in points
            ],
        )
    conn.commit()
    return len(points)


def run(dsn: str | None = None) -> dict[str, object]:
    log = get_logger().bind(source="maud")
    started = time.perf_counter()

    matters, points = parse_maud()
    located = sum(1 for p in points if p.source_span_start is not None)
    anchored = sum(1 for p in points if p.span_kind == ANCHORED)

    with psycopg.connect(dsn or settings.database_url) as conn:
        upsert_maud(conn, matters, points)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        conn.execute(
            "INSERT INTO ingest_runs (source, rows_read, rows_upserted, duration_ms, status, "
            "detail) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                "maud",
                len(points),
                len(matters) + len(points),
                duration_ms,
                "ok",
                (
                    f"{located}/{len(points)} deal points with a located source span; "
                    f"{anchored} anchored to the quoted answer text"
                ),
            ),
        )
        conn.commit()

    result: dict[str, object] = {
        "matters": len(matters),
        "deal_points": len(points),
        "deal_point_names": len({p.deal_point_name for p in points}),
        "spans_located": located,
        "spans_null": len(points) - located,
        "spans_anchored": anchored,
        "spans_recorded": located - anchored,
        "with_numeric_value": sum(1 for p in points if p.numeric_value is not None),
        "duration_ms": duration_ms,
    }
    log.info("ingest_maud", **result)
    return result


def main() -> None:
    configure_logging(settings.log_level, to_file=False)
    run()


if __name__ == "__main__":
    main()


__all__ = [
    "ANCHORED",
    "ANCHOR_OUTCOMES",
    "RECORDED",
    "DealPoint",
    "Matter",
    "SpanLocator",
    "clean_excerpt",
    "parse_maud",
    "run",
    "upsert_maud",
]

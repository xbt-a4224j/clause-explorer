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

import csv
import re
import time
from dataclasses import dataclass

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


def _normalize_with_offsets(source: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed text plus, per normalized character, its offset in `source`.

    Built token-wise rather than character-wise on purpose: the per-character version is the
    obvious way to write this and made a full corpus parse take minutes — 152 contracts of
    ~350 KB each is 53 million Python loop iterations. `finditer` + `extend(range(...))`
    pushes the same work into C and takes seconds.
    """
    chars: list[str] = []
    offsets: list[int] = []
    for index, match in enumerate(TOKEN.finditer(source)):
        start = match.start()
        if index:
            chars.append(" ")
            offsets.append(start - 1)
        chars.append(match.group())
        offsets.extend(range(start, match.end()))
    return "".join(chars), offsets


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
    is_inferred: bool = False


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
        span = locator.locate(excerpt)
        points.append(
            DealPoint(
                matter_id=matter_id,
                deal_point_name=deal_point_name,
                position=answer,
                source_span_start=span[0] if span else None,
                source_span_end=span[1] if span else None,
                source_excerpt=excerpt,
                is_inferred=False,
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
"""

UPSERT_DEAL_POINT = """
INSERT INTO deal_points
    (matter_id, deal_point_name, position, source_span_start, source_span_end, is_inferred)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (matter_id, deal_point_name) DO UPDATE SET
    position = EXCLUDED.position,
    source_span_start = EXCLUDED.source_span_start,
    source_span_end = EXCLUDED.source_span_end,
    is_inferred = EXCLUDED.is_inferred
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
                    p.source_span_start,
                    p.source_span_end,
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
                f"{located}/{len(points)} deal points with a located source span",
            ),
        )
        conn.commit()

    result: dict[str, object] = {
        "matters": len(matters),
        "deal_points": len(points),
        "deal_point_names": len({p.deal_point_name for p in points}),
        "spans_located": located,
        "spans_null": len(points) - located,
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
    "DealPoint",
    "Matter",
    "SpanLocator",
    "clean_excerpt",
    "parse_maud",
    "run",
    "upsert_maud",
]

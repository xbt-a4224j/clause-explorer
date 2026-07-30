"""CUAD -> `clauses`: the commercial-terms corpus (#10).

CUAD ships SQuAD-style: one `context` per contract and, per clause category, the expert's
answer with an `answer_start` offset into that context. So `char_start`/`char_end` are
**read**, not reconstructed — the opposite of MAUD (#8), where excerpts had to be anchored
back into the source and 3.8% could not be.

Two decisions carry the rest of this module:

* **Only answered categories become rows.** CUAD asks all 41 categories of all 510 contracts
  (20,910 question rows) and 6,702 are answered. An unanswered category means the clause is
  absent; storing it as a row with empty text would make "this contract has no audit-rights
  clause" indistinguishable from "we have no text for its audit-rights clause".
* **CUAD contracts are not `matters`.** `matters` is the comparable-deals universe — the 152
  merger agreements a partner is pitching against. Putting 510 commercial contracts in there
  would inflate every facet count that reads as "comparable deals". Clauses carry their own
  `source_contract_title` and `source_file`, so they stand alone.

Industry: CUAD ships **none**. `is_inferred_industry` is TRUE on every row and
`folio_industry_code` is currently NULL for all of them — nothing here guesses an industry
from a filename. Populating it is a classification pass whose accuracy has to be measured
(#28), not a keyword table.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import Connection

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings

CUAD_DIR = Path(__file__).resolve().parents[3] / "data" / "cuad"
CUAD_FILE = CUAD_DIR / "CUADv1.json"
CATEGORY_FILE = CUAD_DIR / "category_descriptions.csv"
SOURCE_FILE = "data/cuad/CUADv1.json"


def corpus_available() -> bool:
    return CUAD_FILE.is_file()


@dataclass(frozen=True)
class Clause:
    id: str
    clause_type: str
    text: str
    source_contract_title: str
    source_file: str
    char_start: int
    char_end: int
    folio_industry_code: str | None = None
    is_inferred_industry: bool = True


def clause_id(title: str, clause_type: str, char_start: int, char_end: int) -> str:
    """Deterministic so a re-run upserts rather than duplicating. Hashed because the natural
    key — a 90-character contract title plus a category — makes an unwieldy primary key.

    `char_end` is part of the key, not decoration: 242 CUAD annotations share a start offset
    with another annotation of the same category and differ only in length ("Google" and
    "Google Inc" both at offset 644). Keying on start alone silently collapsed 244 distinct
    expert spans into 13,579 rows.
    """
    raw = f"{title}\x00{clause_type}\x00{char_start}\x00{char_end}"
    return "cuad_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def parse_cuad(path: Path | None = None) -> list[Clause]:
    payload = json.loads((path or CUAD_FILE).read_text(encoding="utf-8"))

    clauses: list[Clause] = []
    for contract in payload["data"]:
        title = contract["title"]
        for paragraph in contract["paragraphs"]:
            for qa in paragraph["qas"]:
                # the category is the suffix of the id, which is `<title>__<category>`
                clause_type = qa["id"].rsplit("__", 1)[-1]
                for answer in qa["answers"]:
                    start = int(answer["answer_start"])
                    text = answer["text"]
                    clauses.append(
                        Clause(
                            id=clause_id(title, clause_type, start, start + len(text)),
                            clause_type=clause_type,
                            text=text,
                            source_contract_title=title,
                            source_file=SOURCE_FILE,
                            char_start=start,
                            char_end=start + len(text),
                        )
                    )
    return clauses


UPSERT_CLAUSE = """
INSERT INTO clauses
    (id, matter_id, corpus, clause_type, text, source_file, char_start, char_end,
     folio_industry_code, is_inferred_industry)
VALUES (%s, NULL, 'cuad', %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    clause_type = EXCLUDED.clause_type,
    text = EXCLUDED.text,
    source_file = EXCLUDED.source_file,
    char_start = EXCLUDED.char_start,
    char_end = EXCLUDED.char_end,
    folio_industry_code = EXCLUDED.folio_industry_code,
    is_inferred_industry = EXCLUDED.is_inferred_industry
"""


def upsert_clauses(conn: Connection, clauses: list[Clause]) -> int:
    """Upsert, then drop any `cuad` clause the corpus no longer produces.

    Upsert alone is not idempotent across a *revision*: ids are content-derived, so changing
    the id scheme — or CUAD re-cutting an annotation — leaves the superseded row behind
    forever, and it keeps answering drill-throughs with text nothing points at. Pruning is
    scoped to `corpus = 'cuad'` so it can never touch MAUD rows.
    """
    with conn.cursor() as cur:
        cur.executemany(
            UPSERT_CLAUSE,
            [
                (
                    c.id,
                    c.clause_type,
                    c.text,
                    c.source_file,
                    c.char_start,
                    c.char_end,
                    c.folio_industry_code,
                    c.is_inferred_industry,
                )
                for c in clauses
            ],
        )
        cur.execute(
            "DELETE FROM clauses WHERE corpus = 'cuad' AND NOT (id = ANY(%s))",
            ([c.id for c in clauses],),
        )
    conn.commit()
    return len(clauses)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(dsn: str | None = None) -> dict[str, object]:
    log = get_logger().bind(source="cuad")
    started = time.perf_counter()

    if not corpus_available():
        raise FileNotFoundError(
            f"{CUAD_FILE} not found — run scripts/download_cuad.sh (see docs/provenance.md)"
        )

    clauses = parse_cuad()
    with psycopg.connect(dsn or settings.database_url) as conn:
        upsert_clauses(conn, clauses)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        conn.execute(
            "INSERT INTO ingest_runs (source, rows_read, rows_upserted, duration_ms, sha256, "
            "status, detail) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                "cuad",
                len(clauses),
                len(clauses),
                duration_ms,
                _sha256(CUAD_DIR / "data.zip") if (CUAD_DIR / "data.zip").exists() else None,
                "ok",
                "industry not inferred for any row",
            ),
        )
        conn.commit()

    result: dict[str, object] = {
        "contracts": len({c.source_contract_title for c in clauses}),
        "clauses": len(clauses),
        "clause_types": len({c.clause_type for c in clauses}),
        "with_industry": sum(1 for c in clauses if c.folio_industry_code),
        "duration_ms": duration_ms,
    }
    log.info("ingest_cuad", **result)
    return result


def main() -> None:
    configure_logging(settings.log_level, to_file=False)
    run()


if __name__ == "__main__":
    main()

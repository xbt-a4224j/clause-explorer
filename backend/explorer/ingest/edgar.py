"""Enrich the 152 matters from SEC EDGAR: industry, signing date, party names (#9).

MAUD ships agreements with no metadata. EDGAR has the same filings and is free, so this is
152 targeted lookups — no crawler, no scraping of search pages.

**Where each field comes from, and how confident it is:**

| field | source | inferred? |
|---|---|---|
| `signing_date` | the agreement's own header text | no — it is in the document |
| `target_name` / `acquirer_name` | the agreement's own header text | no |
| `sic_code` | EDGAR company submissions for the resolved CIK | no — SEC's own code |
| `folio_industry_code` | `data/mappings/sic_to_folio.csv` crosswalk | **yes** |

`is_inferred_industry` is TRUE for every enriched row. SIC is coarse and self-assigned, and a
crosswalk from it to a FOLIO concept is a judgement — presenting that as gold alongside MAUD's
expert labels is exactly the quiet error CLAUDE.md warns about.

Anything that does not resolve stays NULL. There is no default industry bucket: a matter
silently binned into "Manufacturing" pollutes every rollup that touches it.

**Rate limit:** SEC's published fair-access guidance is 10 requests/second. This client uses
**5 requests/second** with a descriptive User-Agent, and caches every response to
`data/edgar/cache/` so re-runs and tests make no network calls at all.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.ingest.maud import clean_excerpt
from explorer.ingest.maud_corpus import contract_paths

ROOT = Path(__file__).resolve().parents[3]
MAPPING_FILE = ROOT / "data" / "mappings" / "sic_to_folio.csv"
CACHE_DIR = ROOT / "data" / "edgar" / "cache"
CIK_INDEX_FILE = ROOT / "data" / "edgar" / "cik-lookup-data.txt"

USER_AGENT = "Clause Explorer research (open source; contact alex4334johnson@gmail.com)"
REQUESTS_PER_SECOND = 5.0  # SEC fair-access guidance is 10/s; half of it, deliberately
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_PATTERN = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)
HEADER_END = re.compile(r"TABLE OF CONTENTS|ARTICLE\s+(?:[IVX]+|\d+)\b", re.IGNORECASE)

CORPORATE_SUFFIXES = (
    "INCORPORATED",
    "CORPORATION",
    "COMPANY",
    "HOLDINGS",
    "GROUP",
    "INC",
    "CORP",
    "LLC",
    "LP",
    "LTD",
    "PLC",
    "NV",
    "SA",
    "AB",
    "CO",
)
# a party whose name says what it is: a shell formed to effect the merger
SUB_MARKERS = (
    "MERGER SUB",
    "MERGERSUB",
    "ACQUISITION",
    "BIDCO",
    "MERGER CORP",
    "SUB,",
    "MERGER PARENT",
    "HOLDCO",
)

_PARTY_SPLIT = re.compile(r",\s+and\s+|,\s*|\s+and\s+|\s*;\s*", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedHeader:
    target_name: str | None
    acquirer_name: str | None
    signing_date: date | None
    parties: tuple[str, ...]


def parse_header(text: str) -> ParsedHeader:
    """Party names and signing date, read out of the agreement's own opening block."""
    head = clean_excerpt(text[:1500]).lstrip("﻿")
    head = HEADER_END.split(head)[0]

    signing_date = _parse_date(head)
    parties = _parties(head)
    if not parties:
        return ParsedHeader(None, None, signing_date, ())

    buy_side, target = _assign_roles(parties)
    return ParsedHeader(target, buy_side, signing_date, tuple(parties))


def _parse_date(head: str) -> date | None:
    match = DATE_PATTERN.search(head)
    if match is None:
        return None
    month = match.group(1).capitalize()
    months = MONTHS.split("|")
    try:
        return date(int(match.group(3)), months.index(month) + 1, int(match.group(2)))
    except ValueError:
        return None


def _parties(head: str) -> list[str]:
    # everything after the agreement title is the party block; the title itself ends at the
    # first "among"/"between"/"by and among"
    match = re.search(
        r"\b(?:by and among|by and between|among|between)\b[:\s]*", head, re.IGNORECASE
    )
    block = head[match.end() :] if match else head
    block = DATE_PATTERN.split(block)[0]
    block = re.sub(r"\b(?:Dated as of|dated)\b.*", "", block, flags=re.IGNORECASE)

    parties: list[str] = []
    for match in PARTY_PATTERN.finditer(block):
        name = _trim_connectives(_extend_suffix(block, match))
        if len(name) >= 4 and name not in parties:
            parties.append(name)
    return parties


# A party name is a run of words ending in a legal suffix. Splitting the block on commas
# instead — the obvious approach — cuts "ADAMAS PHARMACEUTICALS, INC." in half, because the
# comma before "Inc." is part of the name, not a separator.
PARTY_PATTERN = re.compile(
    r"[A-Z][A-Za-z0-9&'’./\-\s]{2,70}?,?\s+"
    r"(?:INCORPORATED|CORPORATION|COMPANY|HOLDINGS|GROUP|INC|CORP|LLC|L\.L\.C\.|LP|L\.P\.|"
    r"LTD|PLC|N\.V\.|S\.A\.|AB|CO)\.?(?![A-Za-z])"
)
CONNECTIVES = ("BY AND AMONG", "AND AMONG", "AMONG", "BETWEEN", "AND", "BY", "THE")

# "ALASKA COMMUNICATIONS SYSTEMS GROUP, INC." matches at ...GROUP, because GROUP is itself a
# legal-ish suffix. Truncating there costs the CIK lookup the exact registrant name, so a
# match is extended over any further suffix that follows it.
TRAILING_SUFFIX = re.compile(
    r"\A,?\s+(?:INCORPORATED|CORPORATION|COMPANY|INC|CORP|LLC|L\.L\.C\.|LP|L\.P\.|LTD|PLC|"
    r"N\.V\.|S\.A\.)\.?(?![A-Za-z])"
)


def _extend_suffix(block: str, match: re.Match[str]) -> str:
    name = match.group(0)
    rest = block[match.end() :]
    while True:
        following = TRAILING_SUFFIX.match(rest)
        if following is None:
            return name
        name += following.group(0)
        rest = rest[following.end() :]


def _trim_connectives(name: str) -> str:
    """Drop a leading `and`/`among` that the pattern swept up with the name."""
    # trailing "." is part of "INC." — strip separators, not the abbreviation mark
    cleaned = name.strip(" ,:\n")
    changed = True
    while changed:
        changed = False
        upper = cleaned.upper()
        for word in CONNECTIVES:
            if upper.startswith(word + " "):
                cleaned = cleaned[len(word) + 1 :].strip(" ,:")
                changed = True
                break
    return cleaned


def _assign_roles(parties: list[str]) -> tuple[str | None, str | None]:
    """(acquirer, target).

    Two rules, in order:

    1. **Shared stem.** A merger sub is formed by the buyer and named after it — SUPERNUS
       PHARMACEUTICALS / SUPERNUS REEF, CARTER INTERMEDIATE / CARTER ACQUISITION. Parties
       sharing a first word are the buy side; the remaining party is the target. This is the
       rule that matters: "the target is listed last" is false often enough to be dangerous
       (ADAMAS is listed first in its own sale).
    2. **Sub markers**, then position — first is the acquirer, last is the target.
    """
    stems: dict[str, list[str]] = {}
    for party in parties:
        stem = re.sub(r"[^A-Z0-9 ]", "", party.upper()).split()
        if stem:
            stems.setdefault(stem[0], []).append(party)

    buy_side = [group for group in stems.values() if len(group) > 1]
    if len(buy_side) == 1:
        remaining = [p for p in parties if p not in buy_side[0]]
        if len(remaining) == 1:
            return buy_side[0][0], remaining[0]

    non_sub = [p for p in parties if not any(m in p.upper() for m in SUB_MARKERS)]
    if len(non_sub) >= 2:
        return non_sub[0], non_sub[-1]
    if len(non_sub) == 1:
        return None, non_sub[0]
    return None, None


_SUFFIX_ALIASES = {"INCORPORATED": "INC", "CORPORATION": "CORP", "COMPANY": "CO", "LIMITED": "LTD"}


def normalize_company_name(name: str) -> str:
    """Upper-cased, punctuation-free, with legal-suffix spellings folded together.

    EDGAR's own index writes `AEGION CORP` where the agreement writes `AEGION CORPORATION`.
    """
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", name).upper()
    words = [_SUFFIX_ALIASES.get(w, w) for w in cleaned.split()]
    return " ".join(words)


def resolve_cik(name: str, index: dict[str, str]) -> str | None:
    """Exact match on the normalized name, then the same name without its legal suffix.

    No fuzzy matching: "AMERICAN NATIONAL INSURANCE" and "AMERICAN NATIONAL GROUP" are
    different registrants, and a near-miss here attaches another company's industry to a
    matter — invisible in the UI and wrong in every rollup.
    """
    normalized = normalize_company_name(name)
    if normalized in index:
        return index[normalized]
    words = normalized.split()
    if words and words[-1] in CORPORATE_SUFFIXES:
        return index.get(" ".join(words[:-1]))
    return None


def load_cik_index(path: Path | None = None) -> dict[str, str]:
    """EDGAR's `cik-lookup-data.txt`: `COMPANY NAME:CIK:` per line, including delisted
    registrants — which most of these targets are, having just been acquired."""
    source = path or CIK_INDEX_FILE
    index: dict[str, str] = {}
    with source.open(encoding="latin-1") as handle:
        for line in handle:
            name, _, rest = line.partition(":")
            cik = rest.strip(": \n")
            if name and cik:
                index.setdefault(normalize_company_name(name), cik.zfill(10))
    return index


class SicFolioMap:
    """The checked-in SIC -> FOLIO crosswalk. Longest prefix wins."""

    def __init__(self, rows: dict[str, str]) -> None:
        self.rows = rows

    @classmethod
    def load(cls, path: Path | None = None) -> SicFolioMap:
        rows: dict[str, str] = {}
        with (path or MAPPING_FILE).open(encoding="utf-8") as handle:
            for row in csv.DictReader(line for line in handle if not line.startswith("#")):
                rows[row["sic"].strip()] = row["folio_code"].strip()
        return cls(rows)

    def resolve(self, sic: str | None) -> str | None:
        if not sic:
            return None
        digits = sic.strip().zfill(4)
        for length in (4, 3, 2):
            code = self.rows.get(digits[:length])
            if code:
                return code
        return None


@dataclass(frozen=True)
class CompanyFacts:
    name: str | None
    sic: str | None
    sic_description: str | None


def submissions_to_facts(payload: dict) -> CompanyFacts:
    return CompanyFacts(
        name=payload.get("name") or None,
        sic=(payload.get("sic") or "").strip() or None,
        sic_description=(payload.get("sicDescription") or "").strip() or None,
    )


class EdgarClient:
    """Cached, rate-limited fetches of company submissions.

    The cache is the offline story: once populated, `make ingest` and the whole test suite
    run with no network. A cached file is never re-fetched, so a filing amended after our
    fetch date does not silently change the numbers under a published result — the fetch date
    is recorded in docs/provenance.md and re-fetching is an explicit `rm` of the cache.
    """

    def __init__(self, cache_dir: Path | None = None, offline: bool = False) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self._last_request = 0.0
        self.requests_made = 0

    def submissions(self, cik: str) -> dict | None:
        cached = self.cache_dir / f"CIK{cik}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        if self.offline:
            return None

        gap = 1.0 / REQUESTS_PER_SECOND - (time.monotonic() - self._last_request)
        if gap > 0:
            time.sleep(gap)
        request = urllib.request.Request(
            SUBMISSIONS_URL.format(cik=cik), headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - a miss is data we do not have, not a crash
            get_logger().warning("edgar_fetch_failed", cik=cik, error=type(exc).__name__)
            return None
        finally:
            self._last_request = time.monotonic()
            self.requests_made += 1

        payload = json.loads(body)
        # cache only the fields used, so the repo's data dir does not fill with filing lists
        slim = {
            k: payload.get(k)
            for k in ("cik", "name", "sic", "sicDescription", "stateOfIncorporation")
        }
        cached.write_text(json.dumps(slim, indent=1), encoding="utf-8")
        return slim


@dataclass(frozen=True)
class Enrichment:
    matter_id: str
    target_name: str | None
    acquirer_name: str | None
    signing_date: date | None
    sic_code: str | None
    folio_industry_code: str | None


def enrich(
    client: EdgarClient | None = None, index: dict[str, str] | None = None
) -> list[Enrichment]:
    cik_index = index if index is not None else load_cik_index()
    edgar = client or EdgarClient()
    mapping = SicFolioMap.load()

    results: list[Enrichment] = []
    for path in contract_paths():
        header = parse_header(path.read_text(encoding="utf-8", errors="replace"))
        sic = None
        identified: str | None = None
        for candidate in _candidates(header):
            cik = resolve_cik(candidate, cik_index)
            if not cik:
                continue
            payload = edgar.submissions(cik)
            facts = submissions_to_facts(payload) if payload else None
            if facts and facts.sic:
                sic, identified = facts.sic, candidate
                break
        results.append(
            Enrichment(
                matter_id=path.stem,
                target_name=identified or header.target_name,
                acquirer_name=header.acquirer_name,
                signing_date=header.signing_date,
                sic_code=sic,
                folio_industry_code=mapping.resolve(sic),
            )
        )
    return results


def _candidates(header: ParsedHeader) -> list[str]:
    """Parties to try against EDGAR, best guess first.

    MAUD is a *public target* study, so the target is an SEC registrant with an assigned SIC
    code. Merger subs are excluded — a shell formed last month has no SIC — and the remaining
    parties are tried last-listed first, which is where the target sits in the majority of
    these headers. Accepting the first party that resolves *with an SIC* means a matter is
    never enriched from a company EDGAR does not classify.

    Measured on a 20-matter hand check (docs/worklog.md #9): the identified registrant is the
    target in 17, the acquirer in 3. Those three carry the acquirer's industry, which is a
    real error — recorded rather than hidden, and the reason `is_inferred_industry` is TRUE.
    """
    ordered: list[str] = []
    if header.target_name:
        ordered.append(header.target_name)
    for party in reversed(header.parties):
        if any(marker in party.upper() for marker in SUB_MARKERS):
            continue
        if party not in ordered:
            ordered.append(party)
    return ordered


UPDATE_MATTER = """
UPDATE matters SET
    target_name = %s,
    acquirer_name = %s,
    signing_date = %s,
    sic_code = %s,
    folio_industry_code = %s,
    is_inferred_industry = %s
WHERE id = %s
  AND (target_name, acquirer_name, signing_date, sic_code, folio_industry_code,
       is_inferred_industry)
      IS DISTINCT FROM (%s, %s, %s, %s, %s, %s)
"""


def upsert_enrichment(conn: psycopg.Connection, rows: list[Enrichment]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            UPDATE_MATTER,
            [
                (
                    r.target_name,
                    r.acquirer_name,
                    r.signing_date,
                    r.sic_code,
                    r.folio_industry_code,
                    r.folio_industry_code is not None,
                    r.matter_id,
                    # repeated for the IS DISTINCT FROM guard: an unconditional UPDATE bumps
                    # updated_at on all 152 rows every run, and Cube's refresh_key is
                    # MAX(updated_at) — every re-ingest would invalidate every aggregate (#14)
                    r.target_name,
                    r.acquirer_name,
                    r.signing_date,
                    r.sic_code,
                    r.folio_industry_code,
                    r.folio_industry_code is not None,
                )
                for r in rows
            ],
        )
    conn.commit()
    return len(rows)


def run(dsn: str | None = None) -> dict[str, object]:
    log = get_logger().bind(source="edgar")
    started = time.perf_counter()
    client = EdgarClient()
    rows = enrich(client=client)

    with psycopg.connect(dsn or settings.database_url) as conn:
        upsert_enrichment(conn, rows)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        conn.execute(
            "INSERT INTO ingest_runs (source, rows_read, rows_upserted, duration_ms, status, "
            "detail) VALUES (%s, %s, %s, %s, %s, %s)",
            ("edgar", len(rows), len(rows), duration_ms, "ok", f"{client.requests_made} fetches"),
        )
        conn.commit()

    result: dict[str, object] = {
        "matters": len(rows),
        "with_target_name": sum(1 for r in rows if r.target_name),
        "with_signing_date": sum(1 for r in rows if r.signing_date),
        "with_sic": sum(1 for r in rows if r.sic_code),
        "with_folio_industry": sum(1 for r in rows if r.folio_industry_code),
        "network_requests": client.requests_made,
        "duration_ms": duration_ms,
    }
    log.info("ingest_edgar", **result)
    return result


def main() -> None:
    configure_logging(settings.log_level, to_file=False)
    run()


if __name__ == "__main__":
    main()

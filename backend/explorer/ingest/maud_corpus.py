"""Locate and describe the downloaded MAUD corpus (#7).

Everything that needs MAUD on disk goes through here, so there is exactly one place that
knows the layout and one message telling a contributor how to get it.

The corpus is gitignored (155 MB of contracts, CC BY 4.0 but not ours to redistribute in
this repo), so callers must treat absence as normal: `corpus_available()` returns a bool and
tests skip on it rather than failing.
"""

from __future__ import annotations

import csv
import sys
from functools import lru_cache
from pathlib import Path

# data/maud/data/... — the inner `data/` is the archive's own layout, kept as extracted so
# the path in docs/provenance.md matches what unzip produces.
CORPUS_ROOT = Path(__file__).resolve().parents[3] / "data" / "maud" / "data"
CONTRACTS_DIR = CORPUS_ROOT / "contracts"
ARCHIVE = CORPUS_ROOT.parent / "data.zip"

MISSING_MESSAGE = (
    f"MAUD corpus not found at {CORPUS_ROOT} — run scripts/download_maud.sh "
    "(see docs/provenance.md)"
)

# MAUD label rows are one per (contract, deal point, candidate answer). Some `text` fields
# are whole MAE definitions; the default 128 KiB field limit is not enough.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def corpus_available() -> bool:
    return CONTRACTS_DIR.is_dir() and any(CONTRACTS_DIR.glob("contract_*.txt"))


def require_corpus() -> Path:
    if not corpus_available():
        raise FileNotFoundError(MISSING_MESSAGE)
    return CORPUS_ROOT


def contract_paths() -> list[Path]:
    """All contract texts, ordered by contract number rather than lexically."""
    return sorted(
        CONTRACTS_DIR.glob("contract_*.txt"),
        key=lambda p: int(p.stem.removeprefix("contract_")),
    )


def label_csv_paths() -> list[Path]:
    return sorted(CORPUS_ROOT.glob("MAUD_*.csv"))


@lru_cache(maxsize=1)
def deal_point_names() -> tuple[str, ...]:
    """The 92 ABA deal points, read from the corpus — never hardcoded in Python (#8).

    MAUD calls them `question`. A revision that adds a 93rd is then just more rows: a new
    `deal_point_name` dimension value, no schema or code change (CLAUDE.md).
    """
    require_corpus()
    names: set[str] = set()
    for path in label_csv_paths():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                question = row.get("question")
                if question:
                    names.add(question)
    return tuple(sorted(names))


RAW_MAIN_CSV = CORPUS_ROOT / "raw" / "main.csv"

# MAUD's raw spreadsheet names each deal `<Target>_<Acquirer>.pdf` — the only place in the
# corpus that says which side is which. Its `Filename (anon)` column does NOT agree with the
# `contracts/contract_N.txt` numbering (its contract_35.pdf is Michaels/Apollo; the extracted
# contract_35.txt is Performance Food Group/Core-Mark), so the two are joined on annotation
# text instead: raw/main.csv holds the same excerpts the label CSVs carry per contract.
_TITLE_JOIN_SKIP = ("Filename", "Filename (anon)")


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


@lru_cache(maxsize=1)
def _excerpt_owners() -> dict[str, str]:
    """Normalized annotation excerpt -> the single contract it belongs to.

    Excerpts shared by more than one contract are dropped; they cannot identify anything.
    """
    seen: dict[str, set[str]] = {}
    for path in label_csv_paths():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("data_type") != "main":
                    continue
                key = _normalize_ws(row.get("text") or "")
                if key:
                    seen.setdefault(key, set()).add(row["contract_name"])
    return {text: next(iter(ids)) for text, ids in seen.items() if len(ids) == 1}


@lru_cache(maxsize=1)
def deal_titles() -> dict[str, str]:
    """`matter_id -> "<Target>_<Acquirer>.pdf"`, MAUD's own name for the deal.

    A row is attributed only when one contract wins the excerpt vote outright. A tie means we
    do not know whose deal it is, and a wrong title would attach the wrong party's industry —
    the exact failure #42 exists to remove — so a tie yields no title and no enrichment.
    """
    require_corpus()
    owners = _excerpt_owners()
    titles: dict[str, str] = {}
    with RAW_MAIN_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            votes: dict[str, int] = {}
            for column, value in row.items():
                if column in _TITLE_JOIN_SKIP or not value:
                    continue
                owner = owners.get(_normalize_ws(value))
                if owner:
                    votes[owner] = votes.get(owner, 0) + 1
            if not votes:
                continue
            ranked = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
            if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
                continue
            titles.setdefault(ranked[0][0], row["Filename"])
    return titles

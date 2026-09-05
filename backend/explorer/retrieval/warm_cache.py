"""Embed the corpus once and commit the vectors (#16).

`python -m explorer.retrieval.warm_cache`

This is the **only** thing that writes `data/embeddings/vectors.npz`. Query paths never do,
so a run with an API key cannot quietly change a file that is under version control — if the
cache changes, someone ran this deliberately and the diff says so.

What gets embedded:

* one summary line per matter — title, parties, industry, year — which is what comparable-deal
  ranking scores against (#18)
* a deterministic set of free-text descriptions of real matters, so `/comparables` free-text
  ranking is exercisable with no key — with no key only cached text can be ranked (#16)
* the filter-value terms #25's exact/alias/embedding resolution ladder is matched against

Requires `OPENAI_API_KEY`. Everything downstream then runs without one.
"""

from __future__ import annotations

import argparse
import time

import psycopg

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.retrieval.embeddings import EmbeddingCache, content_key

MATTER_SUMMARY_SQL = """
SELECT m.id,
       concat_ws(' · ',
           m.source_contract_title,
           nullif(concat_ws(' / ', m.target_name, m.acquirer_name), ''),
           f.label,
           to_char(m.signing_date, 'YYYY')
       ) AS summary
FROM matters m
LEFT JOIN folio_concepts f ON f.code = m.folio_industry_code
ORDER BY m.id
"""

# Free-text descriptions of real matters. A description the caller types has to be embedded
# before it can be ranked, and with no API key only cached text can be ranked (#16) — so these
# are what makes `/comparables` free-text ranking demonstrable and testable keyless.
#
# These templates lived in `evals/retrieval_set.py`, which #53 deleted along with the retrieval
# ablation. The sampling and the wording are reproduced here **unchanged and deliberately**: the
# vector file is committed, so any drift in the text would make a re-run of this module add
# entries and rewrite a version-controlled artefact.
RANKING_PROBE_SQL = """
SELECT m.target_name,
       m.acquirer_name,
       f.label AS industry,
       to_char(m.signing_date, 'YYYY') AS year
FROM matters m
LEFT JOIN folio_concepts f ON f.code = m.folio_industry_code
WHERE m.target_name IS NOT NULL
  AND m.acquirer_name IS NOT NULL
  AND m.signing_date IS NOT NULL
  AND f.label IS NOT NULL
ORDER BY m.id
"""

PROBE_SAMPLE_SIZE = 30  # every nth qualifying matter, so the set is stable across machines

# The distinct industry labels actually used on matters — not the 18k-concept ontology
# (CLAUDE.md: map five or six dimensions, do not attempt the ontology). This is the closed
# vocabulary #25's embedding-resolution tier matches a free-text filter value against.
INDUSTRY_LABEL_SQL = """
SELECT DISTINCT f.label
FROM matters m
JOIN folio_concepts f ON f.code = m.folio_industry_code
WHERE f.label IS NOT NULL
"""

# Representative free-text terms a partner or agent might type, so #25's exact/alias/embedding
# resolution ladder is exercisable with no API key. Not exhaustive — the point is coverage of
# the three resolution paths (case variants, spacing, a genuine near-miss), not every synonym.
FILTER_VALUE_EVAL_TERMS = [
    "healthcare",
    "Healthcare",
    "health care",
    "medical devices",
    "life sciences",
    "pharma",
    "manufacturing",
    "financial services",
    "not a real industry at all",
]


def ranking_probe_texts(dsn: str | None = None) -> list[str]:
    """Three phrasings each of a deterministic sample of matters.

    The phrasings differ in how much wording they share with the indexed summary: `parties`
    repeats the company names verbatim, `paraphrase` avoids them. Deterministic sampling —
    every nth qualifying row — so the set is identical on every machine and the committed
    vector file stays reproducible.
    """
    with psycopg.connect(dsn or settings.database_url) as conn:
        rows = conn.execute(RANKING_PROBE_SQL).fetchall()

    step = max(1, len(rows) // PROBE_SAMPLE_SIZE)
    texts: list[str] = []
    for target, acquirer, industry, year in rows[::step][:PROBE_SAMPLE_SIZE]:
        texts.append(f"{target} acquired by {acquirer}")
        texts.append(f"{industry} merger agreement signed in {year}")
        texts.append(f"take-private of a {industry.lower()} company by {acquirer}")
    return texts


def gather_texts(dsn: str | None = None) -> dict[str, str]:
    """Everything the product needs a vector for, keyed by a readable source id."""
    texts: dict[str, str] = {}
    for index, query in enumerate(ranking_probe_texts(dsn)):
        texts[f"rankingprobe:{index}"] = query
    for index, term in enumerate(FILTER_VALUE_EVAL_TERMS):
        texts[f"filterterm:{index}"] = term
    with psycopg.connect(dsn or settings.database_url) as conn:
        for matter_id, summary in conn.execute(MATTER_SUMMARY_SQL):
            if summary:
                texts[f"matter:{matter_id}"] = summary
        for (label,) in conn.execute(INDUSTRY_LABEL_SQL):
            texts[f"industrylabel:{label}"] = label
    return texts


def run(dsn: str | None = None) -> dict[str, object]:
    log = get_logger().bind(step="warm_cache")
    started = time.perf_counter()

    if not settings.has_openai_key:
        raise SystemExit(
            "warm_cache needs OPENAI_API_KEY. Everything else in this project runs without "
            "one — that is the point of the committed cache."
        )

    cache = EmbeddingCache(api_key=settings.openai_api_key)
    texts = gather_texts(dsn)
    before = cache.entry_count

    missing = {key: text for key, text in texts.items() if content_key(text) not in cache._vectors}
    log.info("warm_cache_start", texts=len(texts), already_cached=len(texts) - len(missing))

    ordered = list(missing.values())
    if ordered:
        cache.embed_many(ordered)
    total = cache.save()

    result: dict[str, object] = {
        "texts_seen": len(texts),
        "embedded_now": len(ordered),
        "entries_before": before,
        "entries_after": total,
        "api_calls": cache.api_calls,
        "file_bytes": cache.path.stat().st_size,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    log.info("warm_cache_done", **result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m explorer.retrieval.warm_cache")
    parser.parse_args()
    configure_logging(settings.log_level, to_file=True)
    run()


if __name__ == "__main__":
    main()

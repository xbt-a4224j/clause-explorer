"""Embed the corpus once and commit the vectors (#16).

`python -m explorer.retrieval.warm_cache`

This is the **only** thing that writes `data/embeddings/vectors.npz`. Query paths never do,
so a run with an API key cannot quietly change a file that is under version control — if the
cache changes, someone ran this deliberately and the diff says so.

What gets embedded:

* one summary line per matter — title, parties, industry, year — which is what comparable-deal
  ranking scores against (#18)
* clause text from CUAD, truncated per clause, for clause-level search

Requires `OPENAI_API_KEY`. Everything downstream then runs without one.
"""

from __future__ import annotations

import argparse
import time

import psycopg

from explorer.api.logging import configure_logging, get_logger
from explorer.api.settings import settings
from explorer.retrieval.embeddings import EmbeddingCache, content_key

# Clause text is truncated before embedding: the model's context is not the constraint, cost
# and cache size are, and a clause's first 2,000 characters carry its type and terms.
CLAUSE_CHARS = 2000

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

CLAUSE_SQL = f"""
SELECT id, left(text, {CLAUSE_CHARS}) AS text
FROM clauses
WHERE text <> ''
ORDER BY id
"""

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


def gather_texts(dsn: str | None = None) -> dict[str, str]:
    """Everything the product needs a vector for, keyed by a readable source id.

    Eval queries are included deliberately: the retrieval ablation (#17) must run with no API
    key, and it cannot if the queries it issues are uncached.
    """
    from explorer.evals.retrieval_set import eval_query_texts

    texts: dict[str, str] = {}
    for index, query in enumerate(eval_query_texts(dsn)):
        texts[f"evalquery:{index}"] = query
    for index, term in enumerate(FILTER_VALUE_EVAL_TERMS):
        texts[f"filterterm:{index}"] = term
    with psycopg.connect(dsn or settings.database_url) as conn:
        for matter_id, summary in conn.execute(MATTER_SUMMARY_SQL):
            if summary:
                texts[f"matter:{matter_id}"] = summary
        for clause_id, text in conn.execute(CLAUSE_SQL):
            texts[f"clause:{clause_id}"] = text
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

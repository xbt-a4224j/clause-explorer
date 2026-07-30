"""The retrieval eval set (#17), built from ground truth rather than from my opinion.

Hand-authoring "query -> relevant matters" would mean inventing relevance judgements and then
measuring a retriever against my own guesses. Instead this is a **known-item** set: each query
describes exactly one matter using facts already in the database — target, acquirer, industry,
year — and the single relevant result is that matter. Recall@k and MRR against it are
unambiguous, reproducible by anyone with the corpus, and cannot be nudged.

What that measures and what it does not: known-item retrieval tests whether the ranker can find
a specific deal from a description of it. It does **not** measure topical relevance ("deals
like this one"), which needs judgements this corpus does not carry. #18's comparable-deal
ranking is the topical case and is evaluated separately — the limitation is stated in
`docs/results/retrieval-ablation.md` rather than papered over.

Queries are deterministic, so they are embedded once by `warm_cache` and the whole ablation
runs with no API key.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from explorer.api.settings import settings

# One query per template per sampled matter. The templates vary how much lexical overlap the
# query shares with the indexed summary, which is exactly what separates BM25 from vectors:
# `parties` repeats names verbatim (BM25's home ground), `paraphrase` avoids them (vectors').
QUERY_SQL = """
SELECT m.id,
       m.target_name,
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

SAMPLE_SIZE = 30  # every third qualifying matter, deterministic — see build_eval_set


@dataclass(frozen=True)
class EvalQuery:
    query: str
    relevant_matter_id: str
    template: str


def build_eval_set(dsn: str | None = None) -> list[EvalQuery]:
    with psycopg.connect(dsn or settings.database_url) as conn:
        rows = conn.execute(QUERY_SQL).fetchall()

    # deterministic sample: every nth row, so the set is stable across runs and machines and
    # nobody can reshuffle it until the numbers improve
    step = max(1, len(rows) // SAMPLE_SIZE)
    sampled = rows[::step][:SAMPLE_SIZE]

    queries: list[EvalQuery] = []
    for matter_id, target, acquirer, industry, year in sampled:
        queries.append(
            EvalQuery(
                query=f"{target} acquired by {acquirer}",
                relevant_matter_id=matter_id,
                template="parties",
            )
        )
        queries.append(
            EvalQuery(
                query=f"{industry} merger agreement signed in {year}",
                relevant_matter_id=matter_id,
                template="industry_year",
            )
        )
        queries.append(
            EvalQuery(
                query=f"take-private of a {industry.lower()} company by {acquirer}",
                relevant_matter_id=matter_id,
                template="paraphrase",
            )
        )
    return queries


def eval_query_texts(dsn: str | None = None) -> list[str]:
    """Just the strings, for warm_cache to embed so the ablation runs with no key."""
    return [q.query for q in build_eval_set(dsn)]

"""This corpus's hybrid index: the platform's machinery, bound to what a MATTER's text is.

The blending, normalization and caching moved to `semantic_explorer_base.retrieval` — they carried
no legal vocabulary at all, which is the same finding `shape.py` produced one layer down. What
stays here is the only part that was ever domain knowledge: the SQL that says a matter's
searchable text is its title, its two party names, its industry and its signing year.
"""

from __future__ import annotations

from semantic_explorer_base.retrieval import DEFAULT_ALPHA, HybridIndex, Scored, normalize, tokenize
from semantic_explorer_base.retrieval.embeddings import EmbeddingCache

from explorer.api.settings import settings
from explorer.retrieval.embeddings import default_cache

__all__ = ["DEFAULT_ALPHA", "HybridIndex", "MATTER_SUMMARY_SQL", "Scored", "index_from_postgres",
           "normalize", "tokenize"]

MATTER_SUMMARY_SQL = """
SELECT m.id,
       concat_ws(' · ',
           m.source_title,
           nullif(concat_ws(' / ', m.target_name, m.acquirer_name), ''),
           i.label,
           to_char(m.signing_date, 'YYYY')
       ) AS summary
FROM records m
LEFT JOIN categories i ON i.code = m.category_code
ORDER BY m.id
"""


def index_from_postgres(dsn: str | None = None, cache: EmbeddingCache | None = None) -> HybridIndex:
    return HybridIndex.from_postgres(
        dsn or settings.database_url, MATTER_SUMMARY_SQL, cache=cache or default_cache()
    )

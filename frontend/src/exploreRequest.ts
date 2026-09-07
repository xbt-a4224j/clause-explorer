/**
 * How this domain's filters become `/facets` and `/comparables` request bodies, and how the
 * resolved query reads. Extracted from `Explore.tsx` itself when the platform genericised that
 * view (semantic-explorer-base's Explore fix, 2026-09-07, same week as the Shell extraction) —
 * this repo's OWN behavior is unchanged, it just now supplies the reshaping instead of the
 * platform hardcoding it.
 *
 * Filter STATE is keyed by the facet's own GROUP KEY (`industry`, `year`, `consideration`,
 * `band` — see `facets.py`'s `_group()` calls), because that is what Explore's generic
 * `toggle()` writes: `next[group] = value`. The WIRE field names this backend's endpoints
 * actually read (`folio_industry_label`, `signing_year`, `deal_size_band`,
 * `consideration_type`, `signed_from`/`signed_to`) are a separate vocabulary, and translating
 * between the two is this file's entire job. Getting this distinction wrong once already broke
 * one test — the industry code travelled as `filters.industry_code` internally and
 * `folio_industry_code` on the wire, and the first version of this file read the wire name from
 * internal state, which is always undefined.
 */

import type { ComparablesResponse, ExploreFilters } from '@semantic-explorer-base/ui'

export function toExploreRequestFilters(filters: ExploreFilters): {
  facets: Record<string, unknown>
  comparables: Record<string, unknown>
} {
  const year = filters.year ? Number(filters.year) : null
  return {
    facets: {
      folio_industry_label: filters.industry,
      signing_year: year,
      deal_size_band: filters.band,
      consideration_type: filters.consideration,
    },
    comparables: {
      folio_industry_code: filters.industry_code,
      signed_from: year ? `${year}-01-01` : null,
      signed_to: year ? `${year}-12-31` : null,
      deal_size_band: filters.band,
      consideration_type: filters.consideration,
    },
  }
}

export function describeExploreQuery(
  results: ComparablesResponse,
  filters: ExploreFilters,
): string {
  const parts: string[] = []
  const applied = results.applied_filters as Record<string, unknown>
  if (filters.industry) parts.push(filters.industry)
  if (applied.signed_from) parts.push(`signed ${applied.signed_from} to ${applied.signed_to}`)
  if (applied.consideration_type) parts.push(String(applied.consideration_type))
  if (applied.deal_size_band) parts.push(String(applied.deal_size_band))
  if (applied.ranked_by) parts.push(String(applied.ranked_by))
  return `${parts.join(' · ')} · n=${results.candidate_count}`
}

/**
 * The three settings of one knob, named for what they do rather than for their algorithm.
 * Both halves score the same candidate set and are min-max normalised per query before they
 * are blended, because BM25 is unbounded and cosine sits in [0,1] — measured on this corpus,
 * BM25's spread is about 25x cosine's, so blending the raw numbers makes alpha a decoration.
 */
export const EXPLORE_RANKERS = [
  {
    name: 'Keyword',
    tone: 'exact',
    alpha: 0,
    why: 'BM25 only. Finds the words you typed. Misses a deal that says the same thing differently.',
  },
  {
    name: 'Hybrid',
    tone: 'hybrid',
    alpha: 0.5,
    why: 'Both, blended after each is normalised for this query. The default.',
  },
  {
    name: 'Meaning',
    tone: 'meaning',
    alpha: 1,
    why: 'Embeddings only. Finds deals that read like yours, and will happily rank one that shares no words with it.',
  },
] as const

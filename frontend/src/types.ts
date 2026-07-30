/** Shapes returned by the API. Mirrors the pydantic models in backend/explorer/api/. */

export interface FacetValue {
  value: string
  n: number
  selected: boolean
  /** Stable identifier to filter by. Null for buckets with no concept behind them. */
  code?: string | null
}

export interface FacetGroup {
  key: string
  label: string
  values: FacetValue[]
  total_n: number
  /** Set when the group has nothing worth filtering on, with the reason. Renders disabled. */
  unavailable?: string | null
}

/** What a facet click selects: the label is shown, the code is what gets filtered by. */
export interface FacetSelection {
  value: string
  code: string | null
}

export interface FacetsResponse {
  groups: FacetGroup[]
  total_n: number
  unfiltered_n: number
}

export interface Matter {
  matter_id: string
  target_name: string | null
  acquirer_name: string | null
  industry: string | null
  is_inferred_industry: boolean
  signing_date: string | null
  score: number | null
  vector_score: number | null
  bm25_score: number | null
}

export interface AppliedFilters {
  folio_industry_code: string | null
  folio_industry_label: string | null
  rolled_up_to_descendants: number
  deal_size_band: string | null
  signed_from: string | null
  signed_to: string | null
  ranked_by: string
}

export interface ComparablesResponse {
  matters: Matter[]
  candidate_count: number
  returned_count: number
  applied_filters: AppliedFilters
}

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

export interface CorpusCounts {
  matters: number
  deal_points: number
  industries: number
}

export interface FacetsResponse {
  groups: FacetGroup[]
  total_n: number
  unfiltered_n: number
  corpus: CorpusCounts
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

export interface DealPointDetail {
  deal_point_name: string
  position: string
  is_inferred: boolean
  numeric_value: number | null
  source_span_start: number | null
  source_span_end: number | null
  /** The exact characters at [start, end) in the source file. Never generated. */
  clause_text: string | null
  /** Why there is no clause text. Set whenever clause_text is null. */
  text_unavailable: string | null
}

export interface MatterDetail {
  matter_id: string
  target_name: string | null
  acquirer_name: string | null
  industry: string | null
  is_inferred_industry: boolean
  signing_date: string | null
  deal_value_usd: number | null
  source_file: string | null
  source_contract_title: string | null
  deal_point_count: number
  located_count: number
  deal_points: DealPointDetail[]
  /** Plain-text paragraph for pasting into a pitch. Built server-side so it cannot drift. */
  summary: string
}

export interface PositionCount {
  position: string
  n: number
}

export interface NumericSummary {
  numeric_n: number
  median: number | null
  p25: number | null
  p75: number | null
}

export interface DealTermRow {
  deal_point_name: string
  /** Selected matters with a labelled answer. The denominator — not the selection size. */
  answered_n: number
  present_count: number
  /** Pre-rendered server-side per the threshold rule: "6 of 8" or "62%". Never re-derive it. */
  display: string
  display_kind: 'count' | 'percentage'
  positions: PositionCount[]
  numeric: NumericSummary | null
}

export interface DealTermsResponse {
  selection_n: number
  percentage_threshold: number
  rows: DealTermRow[]
  answered_deal_point_count: number
  absent_deal_point_count: number
  scope_note: string
}

export interface DrillMatter {
  matter_id: string
  target_name: string | null
  position: string
  source_file: string | null
  source_span_start: number | null
  source_span_end: number | null
  clause_text: string | null
  text_unavailable: string | null
}

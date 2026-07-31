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
  display_kind: 'count' | 'percentage' | 'low_confidence'
  positions: PositionCount[]
  numeric: NumericSummary | null
  gate_note: string | null
}

export interface DealTermsResponse {
  selection_n: number
  percentage_threshold: number
  min_extraction_confidence: number
  rows: DealTermRow[]
  answered_deal_point_count: number
  absent_deal_point_count: number
  scope_note: string
  refused: boolean
  refusal: Refusal | null
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

export interface CoverageCell {
  column: string
  n: number
  reportable: boolean
  note: string | null
  folio_industry_code: string | null
}

export interface CoverageRow {
  label: string
  folio_industry_code: string | null
  cells: CoverageCell[]
  total_n: number
}

export interface CoverageResponse {
  rows: CoverageRow[]
  columns: string[]
  column_axis: string
  column_note: string
  column_totals: Record<string, number>
  total_n: number
  min_n: number
  thin_cell_count: number
  empty_cell_count: number
}

export interface Refusal {
  reason: string
  n: number
  threshold: number
  message: string
}

export interface AgentFilter {
  member: string
  operator: string
  values: string[]
  /** What the user/agent originally typed for this value, before resolution (#25). */
  raw?: string
  /** True when `values` differs from `raw` — a filter-value resolution actually happened. */
  resolved?: boolean
  inferred?: boolean
}

export interface AgentTimeDimension {
  dimension: string
  range: string
}

export interface AgentSelection {
  measures: string[]
  dimensions: string[]
  filters: AgentFilter[]
  timeDimensions: AgentTimeDimension[]
  n: number
  is_inferred: boolean
}

export interface LabelQueueItem {
  matter_id: string
  deal_point_name: string
  llm_prediction: string
  deterministic_prediction: string
  disagreement: boolean
  quoted_text: string | null
  span_start: number | null
  span_end: number | null
}

export interface LabelQueueResponse {
  items: LabelQueueItem[]
  queue_size: number
  labelled_count: number
}

export interface IngestRun {
  source: string
  rows_read: number
  rows_upserted: number
  duration_ms: number | null
  sha256: string | null
  status: string
  detail: string | null
  started_at: string | null
}

export interface LogLine {
  timestamp?: string
  level?: string
  request_id?: string
  event?: string
  duration_ms?: number
  [key: string]: unknown
}

export interface TableColumn {
  name: string
  type: string
  null_count: number
  is_inferred_flag: boolean
}

export interface TableSchema {
  table: string
  row_count: number
  columns: TableColumn[]
}

export interface TableRowsResponse {
  table: string
  total_count: number
  rows: Record<string, unknown>[]
  limit: number
  offset: number
}

/** `GET /agent/catalog` (#36) — the vocabulary a selection may draw from. */
export interface CatalogEntry {
  name: string
  title: string
  type: string
  cube: string
  description: string
}

export interface CatalogResponse {
  measures: CatalogEntry[]
  dimensions: CatalogEntry[]
  /** measures + dimensions: the discrete label space an offline eval grades against */
  label_space: number
}

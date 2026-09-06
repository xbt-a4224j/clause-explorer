/**
 * This corpus's own types, on top of the platform's.
 *
 * `CorpusRecord` in `@quorum/ui` carries what the PLATFORM needs — an id and the retrieval
 * scores it ranked by. What identifies a matter to a lawyer is here, because no other corpus
 * has a target and an acquirer, and a shared type that named them would be shipping merger
 * vocabulary into every domain that imports it.
 *
 * Everything else re-exports, so a component in this repo still writes one import.
 */
export * from '@quorum/ui'
import type { CorpusRecord, RecordDetail } from '@quorum/ui'

/** A merger agreement, as this app shows it. */
export interface Matter extends CorpusRecord {
  target_name: string | null
  acquirer_name: string | null
  /** Inferred from a SIC crosswalk, never an expert label — hence the flag beside it. */
  industry: string | null
  is_inferred_industry: boolean
  signing_date: string | null
}

/** A matter's detail, with the enrichment fields MAUD and EDGAR carry. */
export interface MatterDetail extends RecordDetail {
  deal_value_usd: number | null
}

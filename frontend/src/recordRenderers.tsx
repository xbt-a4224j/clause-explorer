/**
 * How a merger agreement is drawn on a record card.
 *
 * The card itself is the platform's and is byte-identical to the version a health-claims fork
 * of this app shipped. What differs between the two is only this: which fields identify a
 * record to a reader. A merger corpus shows `target ← acquirer` with an industry chip and a
 * signing date; another corpus shows something else, and neither has to know about the other.
 */
import type { CorpusRecord, RecordDetail } from '@semantic-explorer-base/ui'
import type { Matter, MatterDetail } from './types'

export const RECORD_RENDERERS = {
  title: (record: CorpusRecord) => {
    const matter = record as Matter
    return (
      <>
        {matter.target_name ?? matter.record_id}
        {matter.acquirer_name && <span className="card__acquirer"> ← {matter.acquirer_name}</span>}
      </>
    )
  },

  meta: (record: CorpusRecord) => {
    const matter = record as Matter
    return (
      <>
        {matter.industry && (
          <span className="tag">
            {matter.industry}
            {/* Inferred is never silent. Industry comes from a crosswalk over a coarse
                self-assigned SIC code, not an expert label, and rendering it beside MAUD's gold
                annotations without a marker is the quiet error CLAUDE.md warns about. */}
            {matter.is_inferred_industry && (
              <span
                className="tag__inferred"
                title="derived from SIC via a crosswalk, not an expert label"
              >
                inferred
              </span>
            )}
          </span>
        )}
        {matter.signing_date && <span className="card__date">{matter.signing_date}</span>}
      </>
    )
  },

  footnote: (detail: RecordDetail) =>
    (detail as MatterDetail).deal_value_usd === null ? <> · deal value not available</> : null,

  /**
   * Which deal point carries the answer for a filtered facet.
   *
   * Only consideration has one: industry and signing year come from EDGAR enrichment rather
   * than from a lawyer's answer, so there is no clause to show for them. Omission says that,
   * rather than inventing a link.
   */
  // Keyed by the FACET GROUP's own key ('consideration', from /facets), not the wire field
  // name ('consideration_type') the request body uses -- Explore's generic toggle() writes
  // filter state under the group key, and this map is read against that same state, not
  // against what gets sent over the wire (see exploreRequest.ts's own field renames).
  evidenceFor: { consideration: 'Type of Consideration-Answer' },
}

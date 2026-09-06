import { useEffect, useState } from 'react'
import type { DealPointDetail, Matter, MatterDetail } from '../types'
import { ignoreAbort } from '../abort'

/**
 * One comparable deal, with drill-through to the clauses behind it (#19, #20).
 *
 * Two rules do most of the work here:
 *
 * 1. **Inferred is never silent.** Industry comes from a crosswalk over a coarse self-assigned
 *    SIC code, not an expert label. Rendering it beside MAUD's gold annotations without a
 *    marker is the quiet error CLAUDE.md warns about — and because the copied paragraph leaves
 *    the app and loses the badge, the server writes the word into the text as well.
 * 2. **Missing text says why.** A deal point with no located span renders its reason, not an
 *    empty box. An empty box reads as "no clause"; the truth is "MAUD located no range".
 */
/**
 * The deal point that carries the answer for a filtered dimension.
 *
 * Only consideration has one: industry and signing year come from EDGAR enrichment rather than
 * from a lawyer's answer to a deal point, so there is no clause to show for them and this map
 * says so by omission rather than by inventing a link.
 */
const EVIDENCE_FOR: Record<string, string> = {
  consideration_type: 'Type of Consideration-Answer',
}

export function MatterCard({
  matter,
  focused,
  expanded,
  activeFilter,
  onFocus,
  onToggle,
}: {
  matter: Matter
  /** e.g. `{ dimension: 'consideration_type', value: 'All Cash' }`, when one is applied */
  activeFilter?: { dimension: string; value: string } | null
  focused: boolean
  expanded: boolean
  onFocus: () => void
  onToggle: () => void
}) {
  const [detail, setDetail] = useState<MatterDetail | null>(null)
  const evidenceName = activeFilter ? (EVIDENCE_FOR[activeFilter.dimension] ?? null) : null
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!expanded || detail) return
    // #38
    const controller = new AbortController()
    setError(null)

    fetch(`/api/matters/${encodeURIComponent(matter.matter_id)}`, { signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json()
        if (!response.ok) throw new Error(payload?.error?.message ?? 'could not load deal points')
        // a 200 whose body is not a matter detail (a misrouted proxy, a stale worker) would
        // otherwise crash on .map and take the whole result list down with it
        if (!Array.isArray(payload?.deal_points)) {
          throw new Error('The response did not contain deal points for this matter.')
        }
        return payload as MatterDetail
      })
      .then(setDetail)
      .catch(ignoreAbort((e) => setError(e.message)))

    return () => controller.abort()
  }, [expanded, detail, matter.matter_id])

  async function copySummary() {
    if (!detail) return
    await navigator.clipboard.writeText(detail.summary)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  return (
    <li
      className={`card${focused ? ' is-focused' : ''}`}
      data-testid={`matter-${matter.matter_id}`}
      aria-current={focused ? 'true' : undefined}
    >
      <button
        type="button"
        className="card__hit"
        onClick={onToggle}
        onFocus={onFocus}
        aria-expanded={expanded}
      >
        <span className="card__title">
          {matter.target_name ?? matter.matter_id}
          {matter.acquirer_name && <span className="card__acquirer"> ← {matter.acquirer_name}</span>}
        </span>

        <span className="card__meta">
          {matter.industry && (
            <span className="tag">
              {matter.industry}
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
          {matter.score !== null && (
            <span className="card__score" title="hybrid score within the filtered set">
              {matter.score.toFixed(3)}
            </span>
          )}
        </span>
      </button>

      {expanded && (
        <div className="card__detail">
          {/* why this matter ranked where it did — kept beside the drill-through so the
              ranking is as inspectable as the clauses are */}
          {matter.score !== null && (
            <dl className="card__scores">
              <dt>hybrid</dt>
              <dd>{matter.score.toFixed(3)}</dd>
              <dt>vector</dt>
              <dd>{matter.vector_score?.toFixed(3) ?? '—'}</dd>
              <dt>bm25</dt>
              <dd>{matter.bm25_score?.toFixed(3) ?? '—'}</dd>
            </dl>
          )}

          {error && (
            <div className="state state--error" role="alert">
              <h4 className="state__title">Deal points unavailable</h4>
              <p className="state__body">{error}</p>
            </div>
          )}

          {!error && !detail && (
            <div className="card__loading" aria-label="loading deal points">
              {Array.from({ length: 3 }, (_, i) => (
                <div key={i} className="skeleton skeleton--row" />
              ))}
            </div>
          )}

          {detail && (
            <>
              <div className="card__toolbar">
                <p className="card__provenance">
                  <span className="mono">{detail.located_count} of {detail.deal_point_count}</span>{' '}
                  deal points traced to a source span
                  {detail.deal_value_usd === null && <> · deal value not available</>}
                </p>
                <button type="button" className="card__copy" onClick={copySummary}>
                  {copied ? 'Copied' : 'Copy summary'}
                </button>
              </div>

              <p className="card__cite">
                {detail.source_contract_title}{' '}
                <span className="mono muted">{detail.source_file}</span>
              </p>

              <ul className="dps">
                {orderedDealPoints(detail.deal_points, evidenceName).map((dp) => (
                  <DealPoint
                    key={dp.deal_point_name}
                    dp={dp}
                    sourceFile={detail.source_file}
                    evidenceFor={
                      dp.deal_point_name === evidenceName && activeFilter
                        ? activeFilter.value
                        : undefined
                    }
                  />
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </li>
  )
}

/**
 * One deal point: the answer always, the clause on request.
 *
 * A card rendered every clause for every deal point at once. Measured on `contract_1`, that is
 * 89 deal points carrying **221,045 characters**, so the answer a reader came for was buried in
 * a fifth of a megabyte of contract prose. The answer is the finding; the clause is the evidence
 * for it, and evidence is something you ask to see.
 *
 * `evidenceFor` marks the deal point that justifies a filter the reader has applied. Filtering
 * to All Cash and then not being shown the consideration clause is the product failing its own
 * claim that every figure drills through to the language beneath it, so that one opens by
 * default and says why it is open.
 */
/** The deal point answering the active filter sorts first; the rest keep their order. */
function orderedDealPoints(dps: DealPointDetail[], evidenceName: string | null): DealPointDetail[] {
  if (!evidenceName) return dps
  const hit = dps.filter((d) => d.deal_point_name === evidenceName)
  return hit.length ? [...hit, ...dps.filter((d) => d.deal_point_name !== evidenceName)] : dps
}

function DealPoint({
  dp,
  sourceFile,
  evidenceFor,
}: {
  dp: DealPointDetail
  sourceFile: string | null
  evidenceFor?: string
}) {
  const [open, setOpen] = useState(Boolean(evidenceFor))
  return (
    <li
      className={`dp${evidenceFor ? ' dp--evidence' : ''}`}
      data-testid={`dp-${dp.deal_point_name}`}
    >
      {evidenceFor && (
        <p className="dp__evidence" data-testid="dp-evidence">
          matched on <strong>{evidenceFor}</strong>
        </p>
      )}
      <div className="dp__head">
        <span className="dp__name">{dp.deal_point_name}</span>
        <span className="dp__position">
          {dp.position}
          {dp.is_inferred && (
            <span className="tag__inferred" title="extractor output, not a MAUD expert label">
              inferred
            </span>
          )}
        </span>
      </div>

      {dp.clause_text ? (
        <>
          <button
            type="button"
            className="dp__toggle"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? 'hide the clause' : 'show the clause'}
            <span className="mono muted"> · {dp.clause_text.length.toLocaleString('en-US')} chars</span>
          </button>
          {open && (
            <>
              {/* the clause scrolls inside its own box; the page must never scroll sideways */}
              <blockquote className="dp__clause">{dp.clause_text}</blockquote>
              <p className="dp__span mono muted">
                {sourceFile} [{dp.source_span_start}, {dp.source_span_end})
              </p>
            </>
          )}
        </>
      ) : (
        <p className="dp__missing">{dp.text_unavailable}</p>
      )}
    </li>
  )
}

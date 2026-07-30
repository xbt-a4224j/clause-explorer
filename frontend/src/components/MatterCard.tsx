import { useEffect, useState } from 'react'
import type { DealPointDetail, Matter, MatterDetail } from '../types'

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
export function MatterCard({
  matter,
  focused,
  expanded,
  onFocus,
  onToggle,
}: {
  matter: Matter
  focused: boolean
  expanded: boolean
  onFocus: () => void
  onToggle: () => void
}) {
  const [detail, setDetail] = useState<MatterDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!expanded || detail) return
    let cancelled = false
    setError(null)

    fetch(`/api/matters/${encodeURIComponent(matter.matter_id)}`)
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
      .then((d) => !cancelled && setDetail(d))
      .catch((e: Error) => !cancelled && setError(e.message))

    return () => {
      cancelled = true
    }
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
                {detail.deal_points.map((dp) => (
                  <DealPoint key={dp.deal_point_name} dp={dp} sourceFile={detail.source_file} />
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </li>
  )
}

function DealPoint({ dp, sourceFile }: { dp: DealPointDetail; sourceFile: string | null }) {
  return (
    <li className="dp" data-testid={`dp-${dp.deal_point_name}`}>
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
          {/* the clause scrolls inside its own box; the page must never scroll sideways */}
          <blockquote className="dp__clause">{dp.clause_text}</blockquote>
          <p className="dp__span mono muted">
            {sourceFile} [{dp.source_span_start}, {dp.source_span_end})
          </p>
        </>
      ) : (
        <p className="dp__missing">{dp.text_unavailable}</p>
      )}
    </li>
  )
}

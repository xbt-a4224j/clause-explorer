import { useEffect, useState } from 'react'
import type { DealTermRow, DealTermsResponse, DrillMatter } from '../types'

/**
 * Deal Terms — what was negotiated across the selected set (#21).
 *
 * The rendering rule is the product claim: **"6 of 8", never "75%"**. The server decides which
 * form applies and sends the string pre-rendered, so the rule lives in exactly one place and
 * cannot drift between a table cell, a tooltip and a pasted paragraph. This view does not
 * divide two numbers anywhere — if you find yourself adding a `/`, the rule has already been
 * broken.
 *
 * A deal point nobody in the set negotiated stays on screen as `0 of 8`. "We checked and it is
 * not there" and "we did not check" are indistinguishable once the row disappears.
 */
export function DealTerms({ selection }: { selection: string[] }) {
  const [data, setData] = useState<DealTermsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (selection.length === 0) return
    let cancelled = false
    setData(null)
    setError(null)

    fetch('/api/deal-terms', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ matter_ids: selection }),
    })
      .then(async (response) => {
        const payload = await response.json()
        if (!response.ok) throw new Error(payload?.error?.message ?? 'rollup failed')
        return payload as DealTermsResponse
      })
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message))

    return () => {
      cancelled = true
    }
  }, [selection])

  if (selection.length === 0) {
    return (
      <div className="state state--empty">
        <h3 className="state__title">No deals selected</h3>
        <p className="state__body">
          Select deals in Explore and this rolls up what was negotiated across them. Nothing is
          rolled up over the whole corpus by default — a set you did not choose is not a
          comparable set.
        </p>
      </div>
    )
  }

  return (
    <div className="terms">
      <p className="terms__scope">{data?.scope_note ?? SCOPE_FALLBACK}</p>

      {error && (
        <div className="state state--error" role="alert">
          <h3 className="state__title">Rollup unavailable</h3>
          <p className="state__body">{error}</p>
          <p className="state__hint">
            This is not “no terms found” — the semantic layer did not answer, so no figure here
            would be trustworthy.
          </p>
        </div>
      )}

      {!error && !data && (
        <div className="terms__skeleton" aria-label="loading deal terms">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="skeleton skeleton--row" />
          ))}
        </div>
      )}

      {data && (
        <>
          <p className="terms__caption">
            {data.answered_deal_point_count} deal points answered across{' '}
            <span className="mono">n={data.selection_n}</span> agreements ·{' '}
            {data.absent_deal_point_count} not answered by any of them · counts rather than
            percentages below n={data.percentage_threshold}, because a percentage implies a
            precision this sample does not support
          </p>

          <ul className="terms__list">
            {data.rows.map((row) => (
              <TermRow key={row.deal_point_name} row={row} selection={selection} />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

const SCOPE_FALLBACK =
  'Comparable PUBLIC deals from the MAUD study of SEC-filed merger agreements — ' +
  "not this firm's own matter history."

function TermRow({ row, selection }: { row: DealTermRow; selection: string[] }) {
  const [drilled, setDrilled] = useState<DrillMatter[] | null>(null)
  const [drillError, setDrillError] = useState<string | null>(null)
  const absent = row.answered_n === 0

  async function drill() {
    if (drilled || absent) return
    try {
      const response = await fetch('/api/deal-terms/drill', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ matter_ids: selection, deal_point_name: row.deal_point_name }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.error?.message ?? 'drill-through failed')
      setDrilled(payload.matters)
    } catch (e) {
      setDrillError((e as Error).message)
    }
  }

  return (
    <li className={`term${absent ? ' term--absent' : ''}`} data-testid={`term-${row.deal_point_name}`}>
      <button type="button" className="term__hit" onClick={drill} aria-expanded={drilled !== null}>
        <span className="term__name">{row.deal_point_name}</span>

        <span className="term__figures">
          {/* pre-rendered server-side; this view never divides two numbers */}
          <span className={`term__display term__display--${row.display_kind}`}>{row.display}</span>
          {row.numeric && (
            <span className="term__numeric">
              median {fmt(row.numeric.median)} · {fmt(row.numeric.p25)}–{fmt(row.numeric.p75)} ·{' '}
              <span className="mono">n={row.numeric.numeric_n}</span>
            </span>
          )}
        </span>
      </button>

      {row.positions.length > 0 && (
        <ul className="term__positions">
          {row.positions.map((p) => (
            <li key={p.position} className="term__position">
              <span className="term__poslabel">{p.position}</span>
              <span className="mono muted">n={p.n}</span>
            </li>
          ))}
        </ul>
      )}

      {absent && (
        <p className="term__absent">
          No matter in this set carries a labelled answer for this deal point. Absence is a
          finding, so the row stays.
        </p>
      )}

      {drillError && (
        <p className="term__absent" role="alert">
          {drillError}
        </p>
      )}

      {drilled && (
        <ul className="term__drill">
          {drilled.map((m) => (
            <li key={m.matter_id} className="drill" data-testid={`drill-${m.matter_id}`}>
              <div className="drill__head">
                <span className="drill__party">{m.target_name ?? m.matter_id}</span>
                <span className="term__poslabel">{m.position}</span>
              </div>
              {m.clause_text ? (
                <>
                  {/* the clause scrolls in its own box; the page never scrolls sideways */}
                  <blockquote className="dp__clause">{m.clause_text}</blockquote>
                  <p className="dp__span mono muted">
                    {m.source_file} [{m.source_span_start}, {m.source_span_end})
                  </p>
                </>
              ) : (
                <p className="dp__missing">{m.text_unavailable}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

function fmt(value: number | null): string {
  return value === null ? '—' : String(value)
}

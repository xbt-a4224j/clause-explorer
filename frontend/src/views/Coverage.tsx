import { useEffect, useState } from 'react'
import type { CoverageResponse } from '../types'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { CoverageDiagram } from '../components/diagrams'
import { CoverageExplainer } from '../components/explainers'

/**
 * Coverage — FOLIO industry × period, for KM triage (#22).
 *
 * A deliberate design inversion: default BI styling emphasises the big numbers, but for this
 * audience a gap is more actionable than a strength they already know about. So a thin cell
 * gets a visible marker and a stated reason — never a faded number, which reads as "small" not
 * "not reportable". `min_n` here is the same threshold Deal Terms refuses on (#23), so a KM
 * user knows before clicking whether the rollup behind a cell will decline.
 */
export function Coverage({
  onNavigateToExplore,
}: {
  onNavigateToExplore: (filters: {
    folio_industry_code: string
    folio_industry_label: string
    signing_year: string
  }) => void
}) {
  const [data, setData] = useState<CoverageResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/coverage', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({}),
    })
      .then(async (response) => {
        const payload = await response.json()
        if (!response.ok) throw new Error(payload?.error?.message ?? 'coverage grid failed')
        return payload as CoverageResponse
      })
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <div className="state state--error" role="alert">
      <ExplainerPanel id="coverage" title="What this tab is for: where experience is thin" diagram={<CoverageDiagram />}>
        <CoverageExplainer />
      </ExplainerPanel>
        <h3 className="state__title">Coverage grid unavailable</h3>
        <p className="state__body">{error}</p>
        <p className="state__hint">
          This is not “no coverage” — the semantic layer did not answer, so no cell here would
          be trustworthy.
        </p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="cov__skeleton" aria-label="loading coverage grid">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="skeleton skeleton--row" />
        ))}
      </div>
    )
  }

  if (!Array.isArray(data.rows) || !Array.isArray(data.columns)) {
    return (
      <div className="state state--error" role="alert">
        <h3 className="state__title">Coverage grid unavailable</h3>
        <p className="state__body">The response did not contain a grid.</p>
      </div>
    )
  }

  const cellCount = data.rows.length * data.columns.length

  return (
    <div className="cov">
      <p className="cov__note">{data.column_note}</p>
      <p className="cov__caption">
        {data.thin_cell_count} of {cellCount} cells below n={data.min_n} · {data.empty_cell_count}{' '}
        empty · <span className="mono">n={data.total_n}</span> total
      </p>

      <div className="cov__scroll">
        <table className="cov__table">
          <thead>
            <tr>
              <th scope="col" className="cov__corner">
                industry
              </th>
              {data.columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
              <th scope="col">total</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.label} data-testid={`cov-row-${row.label}`}>
                <th scope="row" className="cov__rowlabel">
                  {row.label}
                </th>
                {row.cells.map((cell) => (
                  <td
                    key={cell.column}
                    data-testid={`cell-${row.label}-${cell.column}`}
                    className={`cov__cell${cell.reportable ? '' : ' cov__cell--thin'}`}
                  >
                    {cell.folio_industry_code ? (
                      <button
                        type="button"
                        className="cov__hit"
                        title={cell.note ?? undefined}
                        onClick={() =>
                          onNavigateToExplore({
                            folio_industry_code: cell.folio_industry_code!,
                            folio_industry_label: row.label,
                            signing_year: cell.column,
                          })
                        }
                      >
                        <span className="mono">{cell.n}</span>
                        {!cell.reportable && (
                          <span className="cov__thinlabel">{cell.note}</span>
                        )}
                      </button>
                    ) : (
                      <span className="mono">{cell.n}</span>
                    )}
                  </td>
                ))}
                <td className="cov__total mono">{row.total_n}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr data-testid="cov-column-totals">
              <th scope="row" className="cov__rowlabel">
                total
              </th>
              {data.columns.map((c) => (
                <td key={c} className="cov__total mono">
                  {data.column_totals[c] ?? 0}
                </td>
              ))}
              <td className="cov__total mono">{data.total_n}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

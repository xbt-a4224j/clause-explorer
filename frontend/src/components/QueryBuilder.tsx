import { useMemo, useState } from 'react'
import type { CatalogEntry, RunSelectionResponse } from '../types'

/**
 * The click-to-build query panel (#37).
 *
 * The catalog rendered as a list is a claim; the catalog rendered as an interface is a
 * demonstration. There is deliberately **no free-text input anywhere in this component** —
 * you select from the vocabulary or you select nothing. That absence is the feature: a
 * reviewer can try to construct an invalid metric and discover there is no affordance for it,
 * which is a stronger argument than being told the model cannot either.
 *
 * The server validates every name again before the query reaches Cube. The missing text box
 * is a property of this UI; the guarantee lives in `api/run_selection.py`.
 */

function Chip({
  entry,
  selected,
  onToggle,
}: {
  entry: CatalogEntry
  selected: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      className={`qb__chip${selected ? ' is-on' : ''}`}
      aria-pressed={selected}
      onClick={onToggle}
      title={entry.description || entry.name}
    >
      <span className="qb__chipname">{entry.name.split('.').slice(1).join('.')}</span>
      <span className="qb__chipcube">{entry.cube}</span>
    </button>
  )
}

export function QueryBuilder({
  measures,
  dimensions,
}: {
  measures: CatalogEntry[]
  dimensions: CatalogEntry[]
}) {
  const [pickedM, setPickedM] = useState<string[]>([])
  const [pickedD, setPickedD] = useState<string[]>([])
  const [result, setResult] = useState<RunSelectionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const query = useMemo(
    () => ({ measures: pickedM, dimensions: pickedD, filters: [] }),
    [pickedM, pickedD],
  )

  function toggle(list: string[], set: (v: string[]) => void, name: string) {
    set(list.includes(name) ? list.filter((x) => x !== name) : [...list, name])
    setResult(null)
    setError(null)
  }

  async function run() {
    setRunning(true)
    setError(null)
    try {
      const r = await fetch('/api/agent/run-selection', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(query),
      })
      const body = await r.json()
      if (!r.ok) throw new Error(body?.detail ?? 'The query was rejected.')
      setResult(body as RunSelectionResponse)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const canRun = pickedM.length > 0 && !running

  return (
    <section className="qb" data-testid="query-builder">
      <h3 className="sem__h">Build a query by clicking</h3>
      <p className="sem__sub">
        There is no text box here, on purpose. You can select from the vocabulary or select
        nothing — the same constraint the model works under. Try to construct a measure that
        does not exist; there is no way to express one.
      </p>

      <h4 className="sem__h4">Measures</h4>
      <div className="qb__chips">
        {measures.map((m) => (
          <Chip
            key={m.name}
            entry={m}
            selected={pickedM.includes(m.name)}
            onToggle={() => toggle(pickedM, setPickedM, m.name)}
          />
        ))}
      </div>

      <h4 className="sem__h4">Group by</h4>
      <div className="qb__chips">
        {dimensions.map((d) => (
          <Chip
            key={d.name}
            entry={d}
            selected={pickedD.includes(d.name)}
            onToggle={() => toggle(pickedD, setPickedD, d.name)}
          />
        ))}
      </div>

      <div className="qb__cols">
        <div>
          <h4 className="sem__h4">The query this builds</h4>
          <pre className="qb__json" data-testid="qb-query">
            {JSON.stringify(query, null, 2)}
          </pre>
          <button type="button" className="qb__run" onClick={run} disabled={!canRun}>
            {running ? 'running…' : 'Run against Postgres'}
          </button>
          {pickedM.length === 0 && (
            <p className="qb__hint">Pick at least one measure — there is nothing to compute yet.</p>
          )}
        </div>

        <div>
          <h4 className="sem__h4">Result</h4>
          {error && (
            <div className="qb__rejected" data-testid="qb-rejected">
              <strong>Rejected before it reached the database.</strong>
              <p>{error}</p>
            </div>
          )}
          {result?.refused && (
            <div className="qb__refused" data-testid="qb-refused">
              <strong>Refused — n={result.n}, threshold {result.threshold}</strong>
              <p>{result.message}</p>
              <p className="qb__hint">
                This is not an empty result. The slice exists; it is too thin to characterize, and
                the gate is server-side — a direct <code>curl</code> gets the same answer.
              </p>
            </div>
          )}
          {result && !result.refused && (
            <>
              <p className="qb__n" data-testid="qb-n">
                {result.n !== null ? (
                  <>
                    n = <span className="mono">{result.n}</span>
                  </>
                ) : (
                  <>no denominator selected — add <code>n</code> to gate on one</>
                )}
              </p>
              <pre className="qb__json" data-testid="qb-rows">
                {JSON.stringify(result.rows, null, 2)}
              </pre>
            </>
          )}
          {!result && !error && (
            <p className="qb__hint">
              Nothing run yet. The number that comes back is computed by Postgres — no model is
              involved in this panel at all.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

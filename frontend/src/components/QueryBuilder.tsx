import { useMemo, useState } from 'react'
import type { CatalogEntry, RunSelectionResponse } from '../types'
import { isAbortError, useAbortOnUnmount } from '../abort'

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
      {/*
        #57's fault 1, in the other picker. This read `n` over `deal_points`, so the three
        different `n` measures in the vocabulary were told apart only by the cube name under
        them, and nothing on the chip said what any of them counted. The catalog has carried a
        title and a description since #36. Title leads; the qualified name — what actually gets
        sent — stays underneath, which is also the Ask chip's shape.
      */}
      <span className="qb__chipname">{entry.title || entry.name}</span>
      <span className="qb__chipcube">{entry.name}</span>
    </button>
  )
}

interface QueryFilter {
  member: string
  operator: string
  values: string[]
}

interface Example {
  question: string
  explains: string
  expect: string
  measures: string[]
  dimensions: string[]
  filters: QueryFilter[]
}

/**
 * Worked examples. Every one was run against the live stack before being written down, and the
 * `expect` line is the observed result — not a plausible-looking guess. If the corpus changes
 * and one of these stops matching, that is a real signal, not a stale string to quietly edit.
 *
 * They exist because 56 names with no starting point is not an interface, it is a reference
 * card. The fourth deliberately fails.
 */
const EXAMPLES: Example[] = [
  {
    question: 'How many of these agreements mention COVID-19 by name?',
    explains:
      'Every deal point is a yes/no or graded answer a lawyer gave. This counts how many of the 152 agreements answered “present” for the pandemic-specific carve-out. The corpus is 2020–21, so this is the question the era forced into every negotiation.',
    expect: '144 of 152',
    measures: ['deal_points.n', 'deal_points.present_count'],
    dimensions: [],
    filters: [
      {
        member: 'deal_points.deal_point_name',
        operator: 'equals',
        values: ['Pandemic or other public health event: Specific reference to COVID-19'],
      },
    ],
  },
  {
    question: 'How long does a target get to match a competing offer?',
    explains:
      'A median, computed by Postgres with percentile_cont — never an average, because on this corpus the two diverge. The units live in the deal point, not the column, which is why you filter to one deal point before taking a median of it.',
    expect: 'median 4 business days, n=147',
    measures: ['deal_points.numeric_n', 'deal_points.median_numeric_value'],
    dimensions: [],
    filters: [
      {
        member: 'deal_points.deal_point_name',
        operator: 'equals',
        values: ['Initial matching rights period (COR)-Answer'],
      },
    ],
  },
  {
    question: 'How many deals do we have in each industry?',
    explains:
      'Industry comes from a checked-in SIC crosswalk, resolved from the SEC’s own code. Note the row with no label: 13 of 152 agreements could not be resolved to an industry at all, and they are shown rather than dropped.',
    expect: 'Health Care 25 · Finance 25 · Manufacturing 22',
    measures: ['comparable_deals.n'],
    dimensions: ['comparable_deals.label'],
    filters: [],
  },
  {
    question: 'What if I narrow it down to a single company?',
    explains:
      'This one is meant to fail. Filtering to one target leaves a sample of one — and an answer describing a single party is that party’s negotiated term, extracted through the analytics layer without opening a document. The server refuses, and it refuses to a raw curl too.',
    expect: 'refused: n=1, threshold 5',
    measures: ['deal_points.n'],
    dimensions: [],
    filters: [
      {
        member: 'deal_points.deal_point_name',
        operator: 'equals',
        values: ['FLS (MAE) Standard-Answer'],
      },
      {
        member: 'comparable_deals.target_name',
        operator: 'equals',
        values: ['TCF FINANCIAL CORPORATION'],
      },
    ],
  },
]

export function QueryBuilder({
  measures,
  dimensions,
}: {
  measures: CatalogEntry[]
  dimensions: CatalogEntry[]
}) {
  const [pickedM, setPickedM] = useState<string[]>([])
  const [pickedD, setPickedD] = useState<string[]>([])
  const [filters, setFilters] = useState<QueryFilter[]>([])
  const [note, setNote] = useState<Example | null>(null)
  const [result, setResult] = useState<RunSelectionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  // #38: this component had no cancel handling of any kind — the query runs from a click, so
  // there was no effect cleanup to hang a guard on
  const nextSignal = useAbortOnUnmount()

  const query = useMemo(
    () => ({ measures: pickedM, dimensions: pickedD, filters }),
    [pickedM, pickedD, filters],
  )

  function load(ex: Example) {
    setPickedM(ex.measures)
    setPickedD(ex.dimensions)
    setFilters(ex.filters)
    setNote(ex)
    setResult(null)
    setError(null)
  }

  function clear() {
    setPickedM([])
    setPickedD([])
    setFilters([])
    setNote(null)
    setResult(null)
    setError(null)
  }

  function toggle(list: string[], set: (v: string[]) => void, name: string) {
    set(list.includes(name) ? list.filter((x) => x !== name) : [...list, name])
    setResult(null)
    setError(null)
    setNote(null)
  }

  async function run() {
    const signal = nextSignal()
    setRunning(true)
    setError(null)
    try {
      const r = await fetch('/api/agent/run-selection', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(query),
        signal,
      })
      const body = await r.json()
      if (!r.ok) throw new Error(body?.detail ?? 'The query was rejected.')
      setResult(body as RunSelectionResponse)
    } catch (e) {
      // an abort is the panel going away or a newer run superseding this one — neither is a
      // rejected query, and showing it in the red "Rejected before it reached the database"
      // box would accuse the semantic layer of something it did not do
      if (isAbortError(e)) return
      setError((e as Error).message)
    } finally {
      if (!signal.aborted) setRunning(false)
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

      <h4 className="sem__h4">Start with a worked example</h4>
      <div className="qb__examples" data-testid="qb-examples">
        {EXAMPLES.map((ex) => (
          <button
            key={ex.question}
            type="button"
            className={`qb__example${note?.question === ex.question ? ' is-on' : ''}`}
            onClick={() => load(ex)}
          >
            <span className="qb__exq">{ex.question}</span>
            <span className="qb__exe">{ex.expect}</span>
          </button>
        ))}
      </div>
      {note && (
        <div className="qb__note" data-testid="qb-note">
          <p>{note.explains}</p>
          <p className="qb__hint">
            Loaded below. Press <strong>Run against Postgres</strong> — expected:{' '}
            <span className="mono">{note.expect}</span>.{' '}
            <button type="button" className="qb__linkbtn" onClick={clear}>
              clear
            </button>
          </p>
        </div>
      )}

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

      {filters.length > 0 && (
        <>
          <h4 className="sem__h4">Filters</h4>
          <div className="qb__chips" data-testid="qb-filters">
            {filters.map((f) => (
              <button
                key={f.member + f.values.join()}
                type="button"
                className="qb__chip is-on"
                onClick={() => {
                  setFilters(filters.filter((x) => x !== f))
                  setNote(null)
                  setResult(null)
                }}
                title="remove this filter"
              >
                <span className="qb__chipname">
                  {f.member.split('.').slice(1).join('.')} = {f.values.join(', ').slice(0, 46)}
                </span>
                <span className="qb__chipcube">click to remove</span>
              </button>
            ))}
          </div>
        </>
      )}

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
            <p className="qb__blocked">
              <strong>Nothing to run yet.</strong> A dimension only says how to <em>group</em> —
              you also need a measure, which is the thing being counted or averaged. Pick one
              above, or load a worked example.
            </p>
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

import { useMemo, useState } from 'react'
import type { AskFilter, AskResponse, RunSelectionResponse } from '../types'
import { isAbortError, useAbortOnUnmount } from '../abort'

/**
 * Ask in words, confirm the reading, then run (#47).
 *
 * The panel below this one builds a query by clicking, and its argument is an *absence*: no
 * text box, so an invalid measure cannot be expressed. This one is the other half. A question
 * goes to the model, which returns a **selection** — never an answer, never a number — and the
 * selection comes back as chips a person edits before anything executes.
 *
 * Three things are load-bearing and easy to lose in a refactor:
 *
 * 1. **`/agent/ask` never executes.** Confirming posts to `/agent/run-selection`, unchanged,
 *    so the validation gate and the `min_n` refusal apply exactly as they do everywhere else.
 * 2. **The confirmation step is not ceremony.** Graded over 25 authored cases, the model runs
 *    0.80 measure precision, 0.692 dimension precision, 0.50 filter exact-match and 0.20
 *    refusal accuracy. Decent at the measure, mediocre at the filter value, bad at declining.
 *    The chips put all three in front of the one person who can catch a misreading.
 * 3. **An unresolved filter value blocks the run.** It never becomes a query returning zero
 *    rows, because zero rows reads as "we have no comparable deals" rather than "you named an
 *    industry this corpus does not carry".
 */

/** Chips carry the short name; the cube prefix is repeated on every one and adds no signal. */
function shortName(name: string) {
  return name.split('.').slice(1).join('.') || name
}

interface EditableFilter extends AskFilter {
  /** true once a person has changed the value — #51 records that as a labelled disagreement */
  edited: boolean
}

interface Confirmed {
  measures: string[]
  dimensions: string[]
  filters: EditableFilter[]
}

function toConfirmed(response: AskResponse): Confirmed {
  return {
    measures: [...response.measures],
    dimensions: [...response.dimensions],
    filters: response.filters.map((f) => ({ ...f, values: [...f.values], edited: false })),
  }
}

/** A filter with no value cannot run: an unresolved value must not become an empty `IN ()`. */
function isBlocked(filters: EditableFilter[]) {
  return filters.some((f) => f.values.length === 0 || f.values.some((v) => !v.trim()))
}

function Resolution({ filter }: { filter: EditableFilter }) {
  const resolution = filter.resolutions[0]
  if (!resolution) return null
  if (filter.edited) return <span className="ask__method">edited by you</span>
  if (resolution.method === 'unresolved') {
    return <span className="ask__method ask__method--unresolved">unresolved</span>
  }
  return (
    <span className="ask__method">
      {resolution.method}
      {resolution.similarity !== null && <> · {resolution.similarity.toFixed(2)}</>}
      {resolution.matter_count !== null && <> · n={resolution.matter_count}</>}
    </span>
  )
}

export function AskBox() {
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [asked, setAsked] = useState<AskResponse | null>(null)
  const [confirmed, setConfirmed] = useState<Confirmed | null>(null)
  const [askError, setAskError] = useState<string | null>(null)
  const [result, setResult] = useState<RunSelectionResponse | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const nextSignal = useAbortOnUnmount()

  const query = useMemo(
    () =>
      confirmed && {
        measures: confirmed.measures,
        dimensions: confirmed.dimensions,
        filters: confirmed.filters.map((f) => ({
          member: f.member,
          operator: f.operator,
          values: f.values,
        })),
      },
    [confirmed],
  )

  async function interpret() {
    if (!question.trim()) return
    const signal = nextSignal()
    setAsking(true)
    setAskError(null)
    setResult(null)
    setRunError(null)
    setAsked(null)
    setConfirmed(null)
    try {
      const r = await fetch('/api/agent/ask', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ question }),
        signal,
      })
      const body = await r.json()
      if (!r.ok) throw new Error(body?.error?.message ?? 'The question could not be interpreted.')
      const response = body as AskResponse
      setAsked(response)
      setConfirmed(toConfirmed(response))
    } catch (e) {
      if (isAbortError(e)) return
      setAskError((e as Error).message)
    } finally {
      if (!signal.aborted) setAsking(false)
    }
  }

  async function run() {
    if (!query) return
    const signal = nextSignal()
    setRunning(true)
    setRunError(null)
    try {
      const r = await fetch('/api/agent/run-selection', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(query),
        signal,
      })
      const body = await r.json()
      if (!r.ok) throw new Error(body?.error?.message ?? 'The selection was rejected.')
      setResult(body as RunSelectionResponse)
    } catch (e) {
      if (isAbortError(e)) return
      setRunError((e as Error).message)
    } finally {
      if (!signal.aborted) setRunning(false)
    }
  }

  function editValue(index: number, value: string) {
    setConfirmed((prev) =>
      prev
        ? {
            ...prev,
            filters: prev.filters.map((f, i) =>
              i === index ? { ...f, values: [value], edited: true } : f,
            ),
          }
        : prev,
    )
    setResult(null)
  }

  function removeFilter(index: number) {
    setConfirmed((prev) =>
      prev ? { ...prev, filters: prev.filters.filter((_, i) => i !== index) } : prev,
    )
    setResult(null)
  }

  function removeFrom(key: 'measures' | 'dimensions', name: string) {
    setConfirmed((prev) =>
      prev ? { ...prev, [key]: prev[key].filter((n) => n !== name) } : prev,
    )
    setResult(null)
  }

  const nothingSelected =
    confirmed !== null &&
    confirmed.measures.length === 0 &&
    confirmed.dimensions.length === 0 &&
    confirmed.filters.length === 0

  const canRun =
    confirmed !== null &&
    confirmed.measures.length > 0 &&
    !isBlocked(confirmed.filters) &&
    !running

  return (
    <section className="ask" data-testid="ask-box">
      <h3 className="sem__h">Ask in words</h3>
      <p className="sem__sub">
        The model reads your question and returns a <strong>selection</strong> — which measure,
        which slice — never an answer and never a number. Check the chips, change what it got
        wrong, and only then does Postgres compute anything.
      </p>

      <div className="ask__row">
        <input
          type="text"
          className="ask__input"
          data-testid="ask-question"
          aria-label="ask a question"
          placeholder="healthcare cash deals, what did boards get on fiduciary outs"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') interpret()
          }}
        />
        <button
          type="button"
          className="qb__run"
          onClick={interpret}
          disabled={asking || !question.trim()}
        >
          {asking ? 'interpreting…' : 'Interpret'}
        </button>
      </div>

      {askError && (
        <div className="qb__rejected" data-testid="ask-error">
          <strong>The question was not interpreted.</strong>
          <p>{askError}</p>
        </div>
      )}

      {confirmed && asked && (
        <>
          <div className="ask__chips" data-testid="ask-chips">
            {nothingSelected && (
              <p className="qb__blocked" data-testid="ask-empty">
                <strong>The model selected nothing.</strong> That is a real outcome, not an
                error — graded over 25 authored cases it declines correctly only 1 time in 5,
                and it also declines when it should not. Rephrase, or build the query by
                clicking below.
              </p>
            )}

            {confirmed.measures.map((m) => (
              <span className="ask__chip" data-testid="chip-measure" key={m}>
                <span className="ask__chiprole">measure</span>
                <span className="ask__chipname">{shortName(m)}</span>
                <button
                  type="button"
                  className="ask__x"
                  aria-label={`remove measure ${shortName(m)}`}
                  onClick={() => removeFrom('measures', m)}
                >
                  ×
                </button>
              </span>
            ))}

            {confirmed.dimensions.map((d) => (
              <span className="ask__chip" data-testid="chip-dimension" key={d}>
                <span className="ask__chiprole">group by</span>
                <span className="ask__chipname">{shortName(d)}</span>
                <button
                  type="button"
                  className="ask__x"
                  aria-label={`remove dimension ${shortName(d)}`}
                  onClick={() => removeFrom('dimensions', d)}
                >
                  ×
                </button>
              </span>
            ))}

            {confirmed.filters.map((f, i) => (
              <span
                className={`ask__chip${f.values.length === 0 ? ' is-unresolved' : ''}`}
                data-testid="chip-filter"
                key={`${f.member}-${i}`}
              >
                <span className="ask__chiprole">{shortName(f.member)}</span>
                <input
                  type="text"
                  className="ask__chipedit"
                  aria-label={`value for ${shortName(f.member)}`}
                  value={f.values[0] ?? ''}
                  onChange={(e) => editValue(i, e.target.value)}
                />
                <Resolution filter={f} />
                {f.resolutions[0]?.method === 'unresolved' && !f.edited && (
                  <span className="ask__near">
                    {f.resolutions[0].candidates.slice(0, 4).map((c) => (
                      <button
                        key={c}
                        type="button"
                        className="ask__nearbtn"
                        onClick={() => editValue(i, c)}
                      >
                        {c}
                      </button>
                    ))}
                  </span>
                )}
                <button
                  type="button"
                  className="ask__x"
                  aria-label={`remove filter ${shortName(f.member)}`}
                  onClick={() => removeFilter(i)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          {asked.blocked_reason && !confirmed.filters.every((f) => f.values.length > 0) && (
            <p className="qb__blocked" data-testid="ask-blocked">
              <strong>Not runnable yet.</strong> {asked.blocked_reason} This is refused rather
              than run: a filter value the corpus does not carry returns zero rows, and zero
              rows reads as “we have no comparable deals”.
            </p>
          )}

          {confirmed.filters.some((f) => f.resolutions[0]?.method === 'verbatim' && !f.edited) && (
            <p className="qb__blocked" data-testid="ask-unchecked">
              <strong>Some values were not checked against the corpus.</strong> The resolution
              ladder has a vocabulary for industry labels and nothing else, so a value on any
              other field is the model&rsquo;s own text. Observed on a live call: it wrote{' '}
              <code>consideration_type = cash</code> where this corpus holds{' '}
              <code>All Cash</code> — which runs, and returns zero rows that read as “we have
              no comparable deals”. Read those chips before running.
            </p>
          )}

          <div className="ask__confirm">
            <button type="button" className="qb__run" onClick={run} disabled={!canRun}>
              {running ? 'running…' : 'Run the confirmed selection'}
            </button>
            <span className="qb__hint">
              Runs through <code>/agent/run-selection</code>, the same path the builder below
              uses — so the validation gate and the <code>min_n</code> refusal still apply.
            </span>
          </div>

          {runError && (
            <div className="qb__rejected" data-testid="ask-rejected">
              <strong>Rejected before it reached the database.</strong>
              <p>{runError}</p>
            </div>
          )}

          {result?.refused && (
            <div className="qb__refused" data-testid="ask-refused">
              <strong>
                Refused — n={result.n}, threshold {result.threshold}
              </strong>
              <p>{result.message}</p>
            </div>
          )}

          {result && !result.refused && (
            <div data-testid="ask-sent">
              <p className="qb__n">
                {result.n !== null ? (
                  <>
                    n = <span className="mono">{result.n}</span>
                  </>
                ) : (
                  <>no denominator selected</>
                )}
              </p>
              <pre className="qb__json" data-testid="ask-rows">
                {JSON.stringify(result.rows, null, 2)}
              </pre>
            </div>
          )}
        </>
      )}
    </section>
  )
}

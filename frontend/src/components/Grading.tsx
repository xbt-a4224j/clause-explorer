import { useEffect, useState } from 'react'
import type { GradingResponse } from '../types'

/**
 * The offline grade (#36).
 *
 * This is the payoff of a fixed vocabulary: correctness is a discrete question, so it can be
 * scored from committed fixtures with no database and no model call. Freeform text-to-SQL has
 * no equivalent — two generated queries can be diffed but not scored, so there is nothing to
 * put in a table like this.
 *
 * Refusal cases are shown apart from the rest rather than averaged in. Refusal accuracy is the
 * worst number here, and it is also the argument for why min_n is enforced server-side rather
 * than asked for in a prompt.
 */
export function Grading() {
  const [data, setData] = useState<GradingResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/agent/grading')
      .then(async (r) => {
        const body = await r.json()
        if (!r.ok) throw new Error(body?.detail ?? 'Grading fixtures are not committed.')
        return body as GradingResponse
      })
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  if (error) {
    return (
      <section className="sem__pane">
        <h3 className="sem__h">Offline grading</h3>
        <p className="sem__sub">{error}</p>
      </section>
    )
  }
  if (!data) return <div className="skeleton skeleton--row" aria-label="loading grading" />

  const refusalBad = data.refusal_correct < data.refusal_total

  return (
    <section className="sem__pane" data-testid="grading">
      <h3 className="sem__h">The grade — computed with no database and no model</h3>
      <p className="sem__sub">{data.note}</p>
      <p className="sem__sub">
        <strong>Read the failures before the score.</strong> Exact-set matching is harsher than
        it looks: <code>q01</code> is marked wrong for choosing{' '}
        <code>count_distinct_matters</code> where the case expected{' '}
        <code>matters_total</code> — and the Cube model documents those two as the same measure
        under different names. A grader that cannot see an alias will punish a correct answer,
        which is itself a finding about the vocabulary rather than about the model.
      </p>

      <div className="grade__tiles">
        <div className="grade__tile">
          <span className="grade__num" data-testid="grade-answerable">
            {data.answerable_correct} of {data.answerable_total}
          </span>
          <span className="grade__lbl">answerable questions, exact selection match</span>
        </div>
        <div className={`grade__tile${refusalBad ? ' is-bad' : ''}`}>
          <span className="grade__num" data-testid="grade-refusal">
            {data.refusal_correct} of {data.refusal_total}
          </span>
          <span className="grade__lbl">
            questions it should have declined — and mostly did not
          </span>
        </div>
      </div>

      {refusalBad && (
        <p className="qb__blocked" data-testid="grade-finding">
          <strong>This is the finding, not a footnote.</strong> The model is bad at knowing when
          to refuse. That is precisely why <code>min_n</code> is enforced in the API rather than
          asked for in a prompt — refusal cannot be the model&rsquo;s job when this is how well
          it does it.
        </p>
      )}

      <div className="scrollx">
        <table className="admin__table grade__table">
          <thead>
            <tr>
              <th>question</th>
              <th>expected</th>
              <th>actual</th>
              <th>ok</th>
            </tr>
          </thead>
          <tbody>
            {data.cases.map((c) => (
              <tr key={c.id} className={c.correct ? '' : 'grade__row--bad'}>
                <td>
                  {c.question}
                  {c.should_refuse && <span className="grade__tag">should refuse</span>}
                </td>
                <td className="mono">
                  {c.should_refuse ? '(nothing)' : c.expected_measures.join(', ') || '—'}
                  {c.expected_dimensions.length > 0 && (
                    <span className="grade__dims">by {c.expected_dimensions.join(', ')}</span>
                  )}
                </td>
                <td className="mono">
                  {c.actual_measures.join(', ') || '(nothing)'}
                  {c.actual_dimensions.length > 0 && (
                    <span className="grade__dims">by {c.actual_dimensions.join(', ')}</span>
                  )}
                </td>
                <td className={c.correct ? 'admin__ok' : 'admin__bad'}>{c.correct ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

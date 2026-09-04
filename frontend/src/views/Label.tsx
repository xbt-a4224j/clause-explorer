import { useEffect, useState } from 'react'
import type { LabelQueueItem, LabelQueueResponse } from '../types'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { LoopDiagram } from '../components/LoopDiagram'

/**
 * Label — the review queue (#29).
 *
 * Improvement has to be cheap or it will not happen. The queue is ranked by disagreement
 * between two extractors (#28's LLM output vs. a free keyword baseline), which needs no
 * calibrated confidence — the cheapest useful signal before #28 has measured one. Every key
 * writes a decision or explicitly skips; there is no confirmation dialog, because the target
 * is under five seconds per item.
 */
export function Label() {
  const [queue, setQueue] = useState<LabelQueueResponse | null>(null)
  const [cursor, setCursor] = useState(0)
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const [showHelp, setShowHelp] = useState(false)
  const [labelledThisSession, setLabelledThisSession] = useState(0)

  useEffect(() => {
    // guarded like Coverage, DealTerms and Explore: without it the response can land after the
    // view is gone and set state on an unmounted component (#38)
    let cancelled = false
    fetch('/api/label/queue')
      .then((r) => r.json())
      .then((d) => !cancelled && setQueue(d))
    return () => {
      cancelled = true
    }
  }, [])

  const item: LabelQueueItem | undefined = queue?.items[cursor]

  async function decide(value: string, priorPrediction: string) {
    if (!item) return
    await fetch('/api/label/decide', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        matter_id: item.matter_id,
        deal_point_name: item.deal_point_name,
        value,
        prior_prediction: priorPrediction,
      }),
    })
    setLabelledThisSession((n) => n + 1)
    setEditing(false)
    setCursor((c) => c + 1)
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null
      const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
      if (typing) return
      if (!item) return

      if (e.key === 'y') {
        e.preventDefault()
        void decide(item.llm_prediction, item.llm_prediction)
      } else if (e.key === 'n' || e.key === 'e') {
        e.preventDefault()
        setEditValue(item.llm_prediction)
        setEditing(true)
      } else if (e.key === 's') {
        e.preventDefault()
        setCursor((c) => c + 1)
      } else if (e.key === '?') {
        e.preventDefault()
        setShowHelp((s) => !s)
      } else if (e.key === 'Escape') {
        setEditing(false)
        setShowHelp(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item])

  if (!queue) return <div className="skeleton skeleton--row" aria-label="loading queue" />

  if (!item) {
    return (
      <div className="state state--empty">
        <h3 className="state__title">Queue is empty</h3>
        <p className="state__body">
          {labelledThisSession} labelled this session · {queue.labelled_count} total.
        </p>
      </div>
    )
  }

  return (
    <div className="label">
      <ExplainerPanel id="label" title="How this queue works" diagram={<LoopDiagram />}>
        <p>
          <strong>What this tab is for.</strong> Improving the extractor without paying for a
          full re-annotation. Two extractors read the same contract — a language model whose
          predictions were recorded to disk, and a keyword baseline that costs nothing — and
          items where they disagree rank to the top, because at least one of them is wrong.
          That is the cheapest useful signal available; it needs no calibrated confidence
          score, which is convenient, because a trustworthy confidence score is exactly what
          we do not have. Every key writes a decision or skips: <code>y n e s</code>.
        </p>
        <p>
          <strong>The limit.</strong> Each decision writes one row to <code>labels</code> and{' '}
          <strong>nothing reads that table yet</strong> — calibration grades against
          MAUD&rsquo;s own answers, not your review. On this corpus it could not: every queued
          item is one of the 20 held-out matters, where a lawyer&rsquo;s answer already exists.
          This is the mechanism you would need on un-annotated firm documents, shown on a
          corpus that does not need it.
        </p>
      </ExplainerPanel>

      <p className="label__progress" data-testid="label-progress">
        <span className="mono">{queue.labelled_count}</span> labelled ·{' '}
        <span className="mono">{cursor}</span> of <span className="mono">{queue.queue_size}</span>{' '}
        in this session
      </p>

      <div className="label__item" data-testid="label-item">
        <p className="label__meta">
          <span className="mono">{item.matter_id}</span> · {item.deal_point_name}
          {item.disagreement && <span className="label__disagree"> · extractors disagree</span>}
        </p>

        {item.quoted_text ? (
          <blockquote className="dp__clause">{item.quoted_text}</blockquote>
        ) : (
          <p className="dp__missing" data-testid="label-nospan">
            No candidate span located — <strong>expected</strong>, not a failure. Some deal
            points are answered from the agreement as a whole rather than one quotable clause.
            Without a span you are judging the answer, not the quotation; open the matter if
            you need the surrounding text.
          </p>
        )}

        {/* why THIS item, in the reviewer's terms — the ranking rationale is otherwise
            visible only in label.py's sort key */}
        <p className="label__why" data-testid="label-why">
          {item.disagreement ? (
            <>
              The two extractors <strong>disagree</strong> — the model answered{' '}
              <span className="mono">{item.llm_prediction}</span>, the keyword baseline
              answered <span className="mono">{item.deterministic_prediction}</span>. One of
              them is wrong, which is why this is ranked first. Your decision settles it.
            </>
          ) : (
            <>
              Both extractors <strong>agree</strong> on{' '}
              <span className="mono">{item.llm_prediction}</span>. You are confirming rather
              than settling a dispute — agreement is cheap to produce and still wrong
              sometimes, so a share of these get checked to keep the accuracy estimate honest.
            </>
          )}
        </p>

        <dl className="label__predictions" data-testid="label-predictions">
          <dt>LLM</dt>
          <dd>{item.llm_prediction}</dd>
          <dt>deterministic</dt>
          <dd>{item.deterministic_prediction}</dd>
        </dl>

        {editing && (
          <div className="label__edit">
            <label htmlFor="label-correct-value">correct value</label>
            <input
              id="label-correct-value"
              aria-label="correct value"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void decide(editValue, item.llm_prediction)
              }}
              autoFocus
            />
          </div>
        )}

        <p className="label__hint">y accept · n reject &amp; correct · e edit · s skip · ? help</p>
      </div>

      {showHelp && (
        <div className="shell__scrim" onClick={() => setShowHelp(false)}>
          <div role="dialog" aria-label="Label shortcuts" className="shell__dialog">
            <h2 className="shell__dialogtitle">Label shortcuts</h2>
            <dl className="shell__keys">
              <div className="shell__keyrow">
                <dt>y</dt>
                <dd>accept the LLM prediction</dd>
              </div>
              <div className="shell__keyrow">
                <dt>n</dt>
                <dd>reject and enter a correction</dd>
              </div>
              <div className="shell__keyrow">
                <dt>e</dt>
                <dd>edit directly</dd>
              </div>
              <div className="shell__keyrow">
                <dt>s</dt>
                <dd>skip, no decision recorded</dd>
              </div>
            </dl>
          </div>
        </div>
      )}
    </div>
  )
}

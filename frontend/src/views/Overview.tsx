import { useEffect, useState } from 'react'
import type { TableRowsResponse } from '../types'
import { ignoreAbort } from '../abort'
import { ProvenanceDiagram, SystemDiagram } from '../components/overviewDiagrams'
import { JOURNEYS, type Journey } from '../journeys'

/**
 * Overview (#39).
 *
 * Every other tab assumes you already know what the system is. A first-time visitor landed
 * on Explore and saw a faceted search over deal data — the two things that make this
 * project worth looking at, hybrid retrieval and the governed semantic layer, were both
 * invisible until you read the repo.
 *
 * This tab is the standing frame, and it is deliberately the only tab that argues rather
 * than demonstrates. It states what the system does not do as plainly as what it does,
 * because "document Q&A tool" is the wrong mental model to carry into Deal Terms and the
 * one a reader will otherwise default to.
 *
 * Counts are read live. A hardcoded corpus size that disagrees with the database would
 * undercut the whole page, since its subject is provenance.
 */

const COUNTED = [
  {
    table: 'matters',
    label: 'matters',
    note: 'merger agreements, each with expert labels',
  },
  {
    table: 'deal_points',
    label: 'deal points',
    note: 'the negotiated terms, modelled long',
  },
] as const

type Counts = Partial<Record<string, number>>

function CorpusStrip() {
  const [counts, setCounts] = useState<Counts>({})
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // #38
    const controller = new AbortController()
    Promise.all(
      COUNTED.map(({ table }) =>
        fetch(`/api/tables/${table}/rows?limit=1`, { signal: controller.signal })
          .then((r) => (r.ok ? (r.json() as Promise<TableRowsResponse>) : Promise.reject(r.status)))
          .then((d) => [table, d.total_count] as const),
      ),
    )
      .then((pairs) => setCounts(Object.fromEntries(pairs)))
      .catch(ignoreAbort(() => setFailed(true)))
    return () => controller.abort()
  }, [])

  if (failed) {
    // Say the counts are unavailable rather than rendering zeros. On a page whose argument
    // is provenance, a plausible wrong number is worse than an absent one.
    return (
      <p className="ov__corpusfail" data-testid="corpus-failed">
        Corpus counts unavailable — the API did not answer. The argument below does not depend on
        them.
      </p>
    )
  }

  return (
    <dl className="ov__corpus" data-testid="corpus-strip">
      {COUNTED.map(({ table, label, note }) => (
        <div className="ov__corpusitem" key={table}>
          <dt className="ov__corpusn">
            {counts[table] === undefined ? '—' : counts[table]!.toLocaleString()}
          </dt>
          <dd className="ov__corpuslabel">
            {label}
            <span className="ov__corpusnote">{note}</span>
          </dd>
        </div>
      ))}
    </dl>
  )
}

function JourneyCard({ journey, onRun }: { journey: Journey; onRun: () => void }) {
  return (
    <li className="jrn" data-testid={`journey-${journey.id}`}>
      <p className="jrn__who">{journey.who}</p>
      <p className="jrn__q">{journey.question}</p>
      <p className="jrn__today">
        <span className="jrn__todaylabel">Today</span> {journey.today}
      </p>

      {/* the clicks, in order — the journey is the diagram */}
      <ol className="jrn__steps" aria-label="the path through the app">
        {journey.steps.map((step) => (
          <li className="jrn__step" key={step}>
            {step}
          </li>
        ))}
      </ol>

      <p className="jrn__outcome">
        <span className="jrn__outlabel">Leaves with</span> {journey.outcome}
      </p>
      {journey.limit && <p className="jrn__limit">{journey.limit}</p>}

      <button type="button" className="jrn__run" onClick={onRun}>
        {journey.cta}
      </button>
    </li>
  )
}

export function Overview({ onStartJourney }: { onStartJourney: (journey: Journey) => void }) {
  return (
    <div className="ov">
      <section className="sem__pane">
        <h3 className="sem__h">What someone would actually do here</h3>
        <p className="sem__sub">
          Two questions, two people who ask them, and the path each one takes. Every journey below
          runs against the corpus that is loaded right now, and each says where it stops.
        </p>
        <ul className="jrn__list" data-testid="journeys">
          {JOURNEYS.map((journey) => (
            <JourneyCard
              key={journey.id}
              journey={journey}
              onRun={() => onStartJourney(journey)}
            />
          ))}
        </ul>
      </section>

      <section className="sem__pane">
        <h3 className="sem__h">What this is</h3>
        <p className="sem__sub">
          A workbench for <strong>&ldquo;what is market?&rdquo;</strong> — the question whose
          reference answer is produced annually, by committee, and read as a PDF. This makes the
          same analysis queryable while keeping the discipline the manual version has: every figure
          carries its sample size, drills through to the clauses underneath it, and the system
          refuses when a slice is too thin.
        </p>
        <CorpusStrip />
      </section>

      <section className="sem__pane">
        <h3 className="sem__h">How it is put together</h3>
        <p className="sem__sub">
          Two ingest sources, one store, then <strong>two independent read paths</strong>. Finding
          the right document and computing a defensible number are different problems, and routing
          both through one generative step inherits the weaknesses of both.
        </p>
        <div className="explain__diagram">
          <SystemDiagram />
        </div>
      </section>

      <section className="sem__pane">
        <h3 className="sem__h">Where a figure comes from</h3>
        <p className="sem__sub">
          Aggregate answers are not generated. A measure is defined once in the semantic layer,
          Postgres computes it, the count of underlying matters travels with the result to the
          screen, and a minimum-sample gate decides whether the figure is shown at all.
        </p>
        <div className="explain__diagram">
          <ProvenanceDiagram />
        </div>
        <p className="sem__sub" data-testid="min-n-prose">
          That threshold is doing three jobs. <strong>Statistical honesty</strong>, so a rollup over
          four deals is not read as a market norm. <strong>Extraction-confidence gating</strong>,
          since thin slices are where label quality matters most and is least verifiable. And{' '}
          <strong>k-anonymity</strong> — an analyst who narrows until one matter remains has
          extracted a single party&rsquo;s negotiated term through the aggregate layer, around the
          ethical wall, without retrieving a document. It is a confidentiality control.
        </p>
      </section>

      <section className="sem__pane">
        <h3 className="sem__h">What it deliberately does not do</h3>
        <ul className="ov__nots" data-testid="boundaries">
          <li>
            <strong>It is not a document Q&amp;A tool.</strong> Retrieval returns documents; the
            semantic layer returns figures. Neither returns a generated paragraph about the corpus.
          </li>
          <li>
            <strong>The model never writes SQL.</strong> It selects from a versioned catalog of
            named measures, which is why its output can be graded offline — see <em>Ask</em>.
          </li>
          <li>
            <strong>Nothing re-extracts the expert labels.</strong> Re-deriving them with a model
            would replace the most reliable thing in the system with the least.
          </li>
          <li>
            <strong>Thin coverage is shown, not smoothed.</strong> On <em>Explore</em> a facet
            value with no matching deals stays on screen, disabled, with the reason stated. A gap
            is a finding, so it is not swept out of the rail.
          </li>
        </ul>
      </section>
    </div>
  )
}

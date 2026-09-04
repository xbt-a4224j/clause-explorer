import { useEffect, useState } from 'react'
import type { CalibrationLabels, IngestRun, LogLine } from '../types'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { AdminDiagram } from '../components/diagrams'
import { ArchitectureDiagram } from '../components/ArchitectureDiagram'
import { AdminExplainer } from '../components/explainers'

/**
 * Admin — ingest status, calibration, evals, live log viewer (#30).
 *
 * Built for one stated reason: so nobody has to open psql. Every number here is read from an
 * artefact another issue already produces (ingest_runs, docs/results/*.md) — this view is
 * composition, not new computation.
 */
export function Admin() {
  return (
    <div className="admin">
      <ExplainerPanel id="admin" title="What this tab is for: did the data land?" diagram={<AdminDiagram />}>
        <AdminExplainer />
      </ExplainerPanel>

      {/* Standalone, outside the collapsible explainer: this is the reference a reader comes
          back to, not something they read once and fold away. */}
      <section className="arch__panel" aria-labelledby="arch-heading">
        <h2 className="admin__heading" id="arch-heading">
          Architecture — what this is made of
        </h2>
        <p className="arch__intro">
          Two readings of the same picture. Top to bottom is the engineering path: four public
          corpora, one idempotent ingest, Postgres, then <strong>two independent query paths</strong>{' '}
          — Cube computes every aggregate, and hybrid retrieval ranks comparable deals without
          going through it, because ranking is not an aggregate. The bottom band is the product
          reading: which question each tab answers, and for whom.
        </p>
        <div className="arch__scroll">
          <ArchitectureDiagram />
        </div>
      </section>
      <IngestStatus />
      <CalibrationReport />
      <LabelLoopCalibration />
      <EvalResults />
      <LogViewer />
    </div>
  )
}

function IngestStatus() {
  const [runs, setRuns] = useState<IngestRun[] | null>(null)

  useEffect(() => {
    // #38: every fetch in this file lacked the cancellation guard the other views already use
    let cancelled = false
    fetch('/api/admin/ingest-status')
      .then((r) => r.json())
      .then((d) => !cancelled && setRuns(d.runs))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="admin__section">
      <h2 className="admin__heading">Ingest status</h2>
      {!runs && <div className="skeleton skeleton--row" aria-label="loading ingest status" />}
      {runs && (
        <table className="admin__table">
          <thead>
            <tr>
              <th>source</th>
              <th>rows upserted</th>
              <th>duration</th>
              <th>sha256</th>
              <th>status</th>
              <th>started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.source}>
                <td>{r.source}</td>
                <td className="mono">{r.rows_upserted}</td>
                <td className="mono">{r.duration_ms ? `${r.duration_ms.toFixed(0)}ms` : '—'}</td>
                <td className="mono admin__sha">{r.sha256 ?? '—'}</td>
                <td className={r.status === 'ok' ? 'admin__ok' : 'admin__bad'}>{r.status}</td>
                <td className="mono">{r.started_at?.slice(0, 19).replace('T', ' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function ReportSection({
  title,
  path,
}: {
  title: string
  path: string
}) {
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch(path)
      .then(async (r) => {
        if (cancelled) return
        if (!r.ok) {
          setMissing(true)
          return
        }
        const body = await r.json()
        if (!cancelled) setMarkdown(body.markdown ?? null)
      })
      .catch(() => !cancelled && setMissing(true))
    return () => {
      cancelled = true
    }
  }, [path])

  return (
    <section className="admin__section">
      <h2 className="admin__heading">{title}</h2>
      {missing && <p className="admin__missing">Not run yet.</p>}
      {markdown && (
        <pre className="admin__report" data-testid="calibration-report">
          {markdown}
        </pre>
      )}
    </section>
  )
}

function CalibrationReport() {
  return <ReportSection title="Calibration" path="/api/admin/calibration" />
}

/**
 * Accuracy per deal point before and after the Label tab's decisions (#41).
 *
 * Read from `docs/results/calibration-labels.json`, which a run of
 * `python -m explorer.evals.calibration` writes — not recomputed here, so the table and the file
 * in the repo cannot become two numbers that disagree.
 *
 * Counts, not percentages: n is 20 per deal point, well under the threshold where a percentage
 * would imply precision the sample does not support.
 */
function LabelLoopCalibration() {
  const [data, setData] = useState<CalibrationLabels | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/admin/calibration-labels')
      .then(async (r) => {
        if (cancelled) return
        if (!r.ok) {
          setMissing(true)
          return
        }
        const body = (await r.json()) as CalibrationLabels
        if (!cancelled) setData(body)
      })
      .catch(() => !cancelled && setMissing(true))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="admin__section">
      <h2 className="admin__heading">Calibration — what human labels changed</h2>

      <p className="admin__note" data-testid="calibration-labels-caveat">
        Grading prefers a Label-tab decision over the model&rsquo;s answer for the same matter and
        deal point, then scores it against MAUD like any other answer — so a mistyped label lowers
        the number rather than being quietly discarded. Read that against what this corpus is:
        every item in the queue is a held-out matter that <strong>already has a lawyer&rsquo;s
        answer</strong>, so reviewing one teaches the system nothing gold did not. The loop closing
        means calibration <em>can</em> prefer a human label; it does not mean this corpus needs one.
        The mechanism earns its keep on <strong>un-annotated</strong> documents, where the
        reviewer&rsquo;s decision is the only answer there is.
      </p>

      {missing && <p className="admin__missing">Not run yet.</p>}
      {!missing && !data && (
        <div className="skeleton skeleton--row" aria-label="loading label calibration" />
      )}

      {data && (
        <>
          <p className="admin__note" data-testid="calibration-labels-summary">
            <span className="mono">{data.labels_applied}</span> labels applied, of which{' '}
            <span className="mono">{data.labels_differing}</span> differed from the model&rsquo;s
            answer. Graded correct{' '}
            <span className="mono">
              {data.correct_before} of {data.prediction_count}
            </span>{' '}
            before,{' '}
            <span className="mono">
              {data.correct_after} of {data.prediction_count}
            </span>{' '}
            after. Produced <span className="mono">{data.generated_at.slice(0, 10)}</span> by{' '}
            <code>{data.command}</code>.
          </p>

          <table className="admin__table" data-testid="calibration-labels">
            <thead>
              <tr>
                <th>deal point</th>
                <th>n</th>
                <th>correct before</th>
                <th>correct after</th>
                <th>labels applied</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.deal_point_name}>
                  <td>{r.deal_point_name}</td>
                  <td className="mono">{r.n}</td>
                  <td className="mono">
                    {r.correct_before} of {r.n}
                  </td>
                  <td className="mono">
                    {r.correct} of {r.n}
                  </td>
                  <td className="mono">{r.labels_applied}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}

function EvalResults() {
  const [gitSha, setGitSha] = useState<string | null>(null)
  const [measureSelection, setMeasureSelection] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/admin/evals')
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return
        setGitSha(d.git_sha)
        setMeasureSelection(d.measure_selection)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="admin__section">
      <h2 className="admin__heading">
        Eval results {gitSha && <span className="mono admin__sha">@ {gitSha}</span>}
      </h2>
      {measureSelection ? (
        <pre className="admin__report">{measureSelection}</pre>
      ) : (
        <p className="admin__missing">Not run yet.</p>
      )}
    </section>
  )
}

function LogViewer() {
  const [lines, setLines] = useState<LogLine[]>([])
  const [totalMatched, setTotalMatched] = useState(0)
  const [level, setLevel] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 50

  useEffect(() => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (level) params.set('level', level)
    if (q) params.set('q', q)
    let cancelled = false
    fetch(`/api/admin/logs?${params}`)
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return
        setLines(d.lines)
        setTotalMatched(d.total_matched)
      })
    return () => {
      cancelled = true
    }
  }, [level, q, offset])

  return (
    <section className="admin__section">
      <h2 className="admin__heading">Logs</h2>
      <div className="admin__logbar">
        <select
          aria-label="filter by level"
          value={level}
          onChange={(e) => {
            setLevel(e.target.value)
            setOffset(0)
          }}
        >
          <option value="">all levels</option>
          <option value="info">info</option>
          <option value="warning">warning</option>
          <option value="error">error</option>
        </select>
        <input
          type="search"
          aria-label="filter logs"
          placeholder="filter…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setOffset(0)
          }}
        />
        <span className="admin__logcount mono">{totalMatched} matched</span>
      </div>

      <table className="admin__table admin__logtable">
        <thead>
          <tr>
            <th>time</th>
            <th>level</th>
            <th>request_id</th>
            <th>event</th>
            <th>duration_ms</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line, i) => (
            <tr key={i}>
              <td className="mono">{String(line.timestamp ?? '').slice(11, 19)}</td>
              <td>{line.level}</td>
              <td className="mono">{line.request_id ?? '—'}</td>
              <td>{line.event}</td>
              <td className="mono">{line.duration_ms ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="admin__pager">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => setOffset((o) => Math.max(0, o - limit))}
        >
          prev
        </button>
        <span className="mono">
          {offset + 1}–{Math.min(offset + limit, totalMatched)} of {totalMatched}
        </span>
        <button
          type="button"
          disabled={offset + limit >= totalMatched}
          onClick={() => setOffset((o) => o + limit)}
        >
          next
        </button>
      </div>
    </section>
  )
}

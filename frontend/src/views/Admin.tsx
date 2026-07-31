import { useEffect, useState } from 'react'
import type { IngestRun, LogLine } from '../types'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { AdminDiagram } from '../components/diagrams'
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
      <IngestStatus />
      <CalibrationReport />
      <EvalResults />
      <LogViewer />
    </div>
  )
}

function IngestStatus() {
  const [runs, setRuns] = useState<IngestRun[] | null>(null)

  useEffect(() => {
    fetch('/api/admin/ingest-status')
      .then((r) => r.json())
      .then((d) => setRuns(d.runs))
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
    fetch(path)
      .then(async (r) => {
        if (!r.ok) {
          setMissing(true)
          return
        }
        const body = await r.json()
        setMarkdown(body.markdown ?? null)
      })
      .catch(() => setMissing(true))
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

function EvalResults() {
  const [gitSha, setGitSha] = useState<string | null>(null)
  const [measureSelection, setMeasureSelection] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/admin/evals')
      .then((r) => r.json())
      .then((d) => {
        setGitSha(d.git_sha)
        setMeasureSelection(d.measure_selection)
      })
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
    fetch(`/api/admin/logs?${params}`)
      .then((r) => r.json())
      .then((d) => {
        setLines(d.lines)
        setTotalMatched(d.total_matched)
      })
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

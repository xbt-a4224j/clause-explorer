import { Fragment, useEffect, useState } from 'react'
import type { CalibrationResponse, IngestRun, LogLine } from '../types'
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

/**
 * Calibration (#44) — the extractor's weakness map, all 92 deal points, worst first.
 *
 * The ordering and the reportable flag are computed by the grader and committed to
 * `docs/eval/calibration_accuracy.json`; this renders them. The same file backs
 * `deal_terms.confidence_lookup()`, so the accuracy on screen is the accuracy in the gate.
 *
 * Two rules this table exists to hold:
 * - Every accuracy carries its own n. A deal point measured on 4 matters and one measured on 20
 *   are not comparable, and a bare percentage hides that.
 * - "Not measured" is its own state, never 0.00. A deal point the run never reached is a
 *   coverage gap, not a failed extraction.
 */
function CalibrationReport() {
  const [report, setReport] = useState<CalibrationResponse | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/admin/calibration')
      .then(async (r) => {
        if (cancelled) return
        if (!r.ok) {
          setMissing(true)
          return
        }
        const body: CalibrationResponse = await r.json()
        if (!cancelled) setReport(body)
      })
      .catch(() => !cancelled && setMissing(true))
    return () => {
      cancelled = true
    }
  }, [])

  const threshold = report?.min_extraction_confidence ?? null
  const results = report?.results ?? []
  // Rows are worst-first, so everything that fails the gate comes before everything that clears
  // it: the line goes immediately above the first reportable row. Drawn as a row rather than
  // left to a column of yes/no, so "below the line" is a position you can see at a glance.
  const firstReportable = results.findIndex((r) => r.measured && r.reportable)

  return (
    <section className="admin__section">
      <h2 className="admin__heading">Calibration</h2>
      {missing && <p className="admin__missing">Not run yet.</p>}
      {report && (
        <>
          <p className="admin__missing" data-testid="calibration-cost">
            {report.measured_deal_point_count} of {report.vocabulary_size} deal points measured ·{' '}
            {report.reportable_count} clear the {threshold?.toFixed(2)} gate ·{' '}
            {report.cost ? (
              <>
                {report.cost.call_count} calls, {report.cost.total_tokens?.toLocaleString()} tokens,{' '}
                ${report.cost.cost_usd?.toFixed(2)} measured
              </>
            ) : (
              'cost not recorded'
            )}
          </p>
          <table className="admin__table" data-testid="calibration-table">
            <thead>
              <tr>
                <th>deal point</th>
                <th>n</th>
                <th>correct</th>
                <th>accuracy</th>
                <th>95% CI</th>
              </tr>
            </thead>
            <tbody>
              {results.map((row, index) => (
                <Fragment key={row.deal_point_name}>
                  {index === firstReportable && threshold !== null && (
                    <tr className="admin__gate-row">
                      <td colSpan={5} data-testid="calibration-gate-line">
                        {threshold.toFixed(2)} extraction-confidence gate — {report.reportable_count}{' '}
                        of {report.measured_deal_point_count} measured deal points clear it.
                        Everything above this line is not reportable from extractor output.
                      </td>
                    </tr>
                  )}
                  <tr className={row.measured && !row.reportable ? 'admin__row--below' : undefined}>
                    <td data-testid="calibration-row-name">{row.deal_point_name}</td>
                    <td className="mono" data-testid="calibration-row-n">
                      {row.n}
                    </td>
                    <td className="mono">{row.measured ? row.correct : '—'}</td>
                    <td className="mono" data-testid="calibration-row-accuracy">
                      {row.measured && row.accuracy !== null ? (
                        row.accuracy.toFixed(2)
                      ) : (
                        <span className="admin__unmeasured">not measured</span>
                      )}
                    </td>
                    <td className="mono">
                      {row.measured && row.ci_low !== null && row.ci_high !== null
                        ? `[${row.ci_low.toFixed(2)}, ${row.ci_high.toFixed(2)}]`
                        : '—'}
                    </td>
                  </tr>
                </Fragment>
              ))}
            </tbody>
          </table>
          <pre className="admin__report" data-testid="calibration-report">
            {report.markdown}
          </pre>
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

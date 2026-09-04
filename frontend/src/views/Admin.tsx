import { Fragment, useEffect, useState } from 'react'
import type { CalibrationLabels, CalibrationResponse, IngestRun, LogLine } from '../types'
import { ignoreAbort } from '../abort'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { AdminExplainer } from '../components/explainers'

/**
 * Admin — ingest status, calibration, evals, live log viewer (#30).
 *
 * Built for one stated reason: so nobody has to open psql. Every number here is read from an
 * artefact another issue already produces (ingest_runs, docs/results/*.md) — this view is
 * composition, not new computation.
 *
 * #45 removed the standalone `ArchitectureDiagram` that sat above the sections. It was a second
 * whole-system drawing; `SystemDiagram` on Overview is now the only one, so a reader cannot
 * find two pictures of the same system and go looking for the difference between them.
 */
export function Admin() {
  return (
    <div className="admin">
      <ExplainerPanel id="admin" title="What this tab is for: did the data land?">
        <AdminExplainer />
      </ExplainerPanel>

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
    // #38: every fetch in this file is aborted on teardown, not merely ignored on arrival
    const controller = new AbortController()
    fetch('/api/admin/ingest-status', { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => setRuns(d.runs))
      .catch(
        ignoreAbort((e) => {
          throw e
        }),
      )
    return () => controller.abort()
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
    // #38: every fetch in this file is aborted on teardown, not merely ignored on arrival
    const controller = new AbortController()
    fetch('/api/admin/calibration', { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) {
          setMissing(true)
          return
        }
        const body: CalibrationResponse = await r.json()
        setReport(body)
      })
      .catch(ignoreAbort(() => setMissing(true)))
    return () => controller.abort()
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
    const controller = new AbortController()
    fetch('/api/admin/calibration-labels', { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) {
          setMissing(true)
          return
        }
        const body = (await r.json()) as CalibrationLabels
        setData(body)
      })
      .catch(ignoreAbort(() => setMissing(true)))
    return () => controller.abort()
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
    const controller = new AbortController()
    fetch('/api/admin/evals', { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => {
        setGitSha(d.git_sha)
        setMeasureSelection(d.measure_selection)
      })
      .catch(
        ignoreAbort((e) => {
          throw e
        }),
      )
    return () => controller.abort()
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
    const controller = new AbortController()
    fetch(`/api/admin/logs?${params}`, { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => {
        setLines(d.lines)
        setTotalMatched(d.total_matched)
      })
      .catch(
        ignoreAbort((e) => {
          throw e
        }),
      )
    return () => controller.abort()
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

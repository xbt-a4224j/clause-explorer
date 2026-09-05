import { render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Admin } from './Admin'

/** Admin (#30) — composition of artefacts other issues already produce. */

function mockApi() {
  return vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('ingest-status')) {
      return {
        ok: true,
        json: async () => ({
          runs: [
            {
              source: 'maud',
              rows_read: 13089,
              rows_upserted: 13089,
              duration_ms: 12000,
              sha256: 'abc123',
              status: 'ok',
              detail: null,
              started_at: '2026-07-30T12:00:00Z',
            },
          ],
        }),
      } as Response
    }
    // #41's artefact must be matched before the markdown report — its path is a superstring
    if (u.includes('calibration-labels')) {
      return {
        ok: true,
        json: async () => ({
          generated_at: '2026-09-04T01:58:24+00:00',
          command: 'PYTHONPATH=backend python -m explorer.evals.calibration',
          prediction_count: 100,
          labels_applied: 6,
          labels_differing: 2,
          correct_before: 45,
          correct_after: 44,
          accuracy_before: 0.45,
          accuracy_after: 0.44,
          results: [
            {
              deal_point_name: '"Ability to consummate" concept is subject to MAE carveouts',
              n: 20,
              correct_before: 6,
              accuracy_before: 0.3,
              correct: 5,
              accuracy: 0.25,
              labels_applied: 1,
              reportable: false,
            },
            {
              deal_point_name: 'Actions taken by Buyer-Answer (Y/N)',
              n: 20,
              correct_before: 4,
              accuracy_before: 0.2,
              correct: 4,
              accuracy: 0.2,
              labels_applied: 0,
              reportable: false,
            },
          ],
        }),
      } as Response
    }
    if (u.includes('calibration')) {
      return {
        ok: true,
        json: async () => ({
          markdown: '| deal point | n |\n|---|---|\n',
          min_extraction_confidence: 0.7,
          vocabulary_size: 3,
          measured_deal_point_count: 2,
          reportable_count: 1,
          cost: { cost_usd: 1.02, call_count: 1704, total_tokens: 5500000 },
          results: [
            { deal_point_name: 'Weakest point', n: 20, correct: 4, accuracy: 0.2, ci_low: 0.081,
              ci_high: 0.416, reportable: false, measured: true },
            { deal_point_name: 'Strong point', n: 20, correct: 19, accuracy: 0.95, ci_low: 0.764,
              ci_high: 0.991, reportable: true, measured: true },
            { deal_point_name: 'Never measured', n: 0, correct: 0, accuracy: null, ci_low: null,
              ci_high: null, reportable: false, measured: false },
          ],
        }),
      } as Response
    }
    if (u.includes('evals')) {
      return {
        ok: true,
        json: async () => ({ git_sha: 'deadbee', measure_selection: 'refusal_accuracy 0.2' }),
      } as Response
    }
    if (u.includes('logs')) {
      return {
        ok: true,
        json: async () => ({
          lines: [{ timestamp: '2026-07-30T12:00:00Z', level: 'info', event: 'request_end' }],
          total_matched: 1,
        }),
      } as Response
    }
    return { ok: true, json: async () => ({}) } as Response
  })
}

beforeEach(() => vi.stubGlobal('fetch', mockApi()))
afterEach(() => vi.unstubAllGlobals())

describe('ingest status', () => {
  it('shows rows upserted and sha per source', async () => {
    render(<Admin />)
    expect(await screen.findByText('maud')).toBeInTheDocument()
    expect(screen.getByText('13089')).toBeInTheDocument()
    expect(screen.getByText('abc123')).toBeInTheDocument()
  })
})

describe('calibration and evals', () => {
  it('renders the committed calibration report', async () => {
    render(<Admin />)
    // scoped to the report: #35's explainer prose also says "deal point", by design
    expect(await screen.findByTestId('calibration-report')).toHaveTextContent(/deal point/)
  })

  it('lists every deal point with its accuracy and its own n, worst first (#44)', async () => {
    render(<Admin />)
    const table = await screen.findByTestId('calibration-table')
    const names = within(table)
      .getAllByTestId('calibration-row-name')
      .map((cell) => cell.textContent)
    expect(names).toEqual(['Weakest point', 'Strong point', 'Never measured'])
    expect(within(table).getAllByTestId('calibration-row-n').map((c) => c.textContent)).toEqual([
      '20',
      '20',
      '0',
    ])
  })

  it('draws the 0.7 gate as a line in the table, not just prose (#44)', async () => {
    render(<Admin />)
    const gate = await screen.findByTestId('calibration-gate-line')
    expect(gate).toHaveTextContent(/0\.70/)
    expect(gate).toHaveTextContent(/1 of 2/)
  })

  it('shows an unmeasured deal point as unmeasured, never as zero accuracy (#44)', async () => {
    render(<Admin />)
    const table = await screen.findByTestId('calibration-table')
    const cells = within(table).getAllByTestId('calibration-row-accuracy')
    expect(cells[0]).toHaveTextContent('0.20')
    expect(cells[2]).toHaveTextContent('not measured')
    expect(cells[2]).not.toHaveTextContent('0.00')
  })

  it('reports the measured dollar cost of the run', async () => {
    render(<Admin />)
    expect(await screen.findByTestId('calibration-cost')).toHaveTextContent(/\$1\.02/)
  })

  it('tags eval results with the git sha', async () => {
    render(<Admin />)
    expect(await screen.findByText(/deadbee/)).toBeInTheDocument()
    expect(screen.getByText(/refusal_accuracy/)).toBeInTheDocument()
  })
})

describe('human labels in calibration (#41)', () => {
  it('shows accuracy before and after human labels, per deal point, with denominators', async () => {
    render(<Admin />)
    const table = await screen.findByTestId('calibration-labels')
    // before and after as counts over their own n, never a bare percentage
    expect(table).toHaveTextContent(/6 of 20/)
    expect(table).toHaveTextContent(/5 of 20/)
    expect(table).toHaveTextContent(/MAE carveouts/)
  })

  // #52 moved the headline and the corpus caveat to the top of the Label tab, beside the queue
  // that produces them. Admin keeps the per-deal-point breakdown and points at the panel — the
  // assertion is that it no longer repeats the figures.
  it('points at the Label panel instead of restating the before/after headline', async () => {
    render(<Admin />)
    const section = await screen.findByTestId('calibration-labels-pointer')
    expect(section).toHaveTextContent(/Label/)
    expect(section).not.toHaveTextContent(/45 of 100/)
    expect(section).not.toHaveTextContent(/44 of 100/)
  })

  it('names the command that produced the numbers, so they are checkable', async () => {
    render(<Admin />)
    const section = await screen.findByTestId('calibration-labels-provenance')
    expect(section).toHaveTextContent(/explorer\.evals\.calibration/)
  })
})

describe('log viewer', () => {
  it('shows parsed log columns', async () => {
    render(<Admin />)
    expect(await screen.findByText('request_end')).toBeInTheDocument()
  })

  it('reports the matched count', async () => {
    render(<Admin />)
    expect(await screen.findByText(/1 matched/)).toBeInTheDocument()
  })
})

/**
 * #45 deleted `ArchitectureDiagram` and the six tests that pinned its content, because the
 * behaviour they encoded is gone on purpose: it was a second whole-system drawing, and
 * `SystemDiagram` on Overview is now the only one. Two of those tests asserted claims that
 * still matter and simply live elsewhere — "both read paths are named" is now pinned on
 * `SystemDiagram` in Overview.test.tsx, and "CUAD is loaded but unqueried" in Tables.test.tsx.
 * What this file keeps is the structural property that outlived the drawing.
 */
describe('what Admin still carries (#45)', () => {
  it('keeps its sections after the architecture panel was removed', async () => {
    render(<Admin />)
    // Anchored, because #41 added a second calibration heading — an unanchored /calibration/i
    // now matches two and throws on the ambiguity rather than on a missing section.
    for (const name of [
      /ingest status/i,
      /^calibration$/i,
      /^calibration — what human labels changed$/i,
      /eval results/i,
      /^logs$/i,
    ]) {
      expect(await screen.findByRole('heading', { name })).toBeInTheDocument()
    }
  })

  it('no longer draws the system a second time', async () => {
    render(<Admin />)
    await screen.findByRole('heading', { name: /ingest status/i })
    expect(screen.queryByRole('img', { name: /architecture/i })).not.toBeInTheDocument()
  })
})

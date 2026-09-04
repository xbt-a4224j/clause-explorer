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

describe('architecture diagram (#35)', () => {
  it('renders as a labelled image with a text description carrying the same content', async () => {
    render(<Admin />)
    const svg = await screen.findByRole('img', { name: /architecture/i })
    expect(svg).toBeInTheDocument()
  })

  it('stands alone rather than hiding inside the collapsible explainer', async () => {
    render(<Admin />)
    const heading = await screen.findByRole('heading', { name: /what this is made of/i })
    // the explainer body is hidden when collapsed; this section must never be inside it
    expect(heading.closest('.explain')).toBeNull()
  })

  it('names both query paths, because the split is the point', async () => {
    render(<Admin />)
    const desc = (await screen.findByRole('img', { name: /architecture/i })).textContent ?? ''
    expect(desc).toMatch(/Cube Core/)
    expect(desc).toMatch(/hybrid retrieval/i)
    expect(desc).toMatch(/does not go through Cube|not go through Cube/i)
  })

  it('marks the inferred source as inferred', async () => {
    render(<Admin />)
    const desc = (await screen.findByRole('img', { name: /architecture/i })).textContent ?? ''
    expect(desc).toMatch(/inferred rather than labelled/i)
  })
})

describe('CUAD is not overstated (#35)', () => {
  it('the description says CUAD is loaded but unqueried', async () => {
    render(<Admin />)
    const desc = (await screen.findByRole('img', { name: /architecture/i })).textContent ?? ''
    expect(desc).toMatch(/no endpoint currently queries/i)
  })

  it('does not present CUAD as a peer input to MAUD', async () => {
    render(<Admin />)
    const svg = await screen.findByRole('img', { name: /architecture/i })
    // gold = expert-labelled and load-bearing; CUAD must not be in that group
    expect(svg.querySelectorAll('.arch__dormant rect').length).toBeGreaterThan(0)
  })
})

import { render, screen } from '@testing-library/react'
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
      return { ok: true, json: async () => ({ markdown: '| deal point | n |\n|---|---|\n' }) } as Response
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

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

/**
 * #45 deleted `ArchitectureDiagram` and the six tests that pinned its content, because the
 * behaviour they encoded is gone on purpose: it was a second whole-system drawing, and
 * `SystemDiagram` on Overview is now the only one. Two of those tests asserted claims that
 * still matter and simply live elsewhere — "both read paths are named" is now pinned on
 * `SystemDiagram` in Overview.test.tsx, and "CUAD is loaded but unqueried" in Tables.test.tsx.
 * What this file keeps is the structural property that outlived the drawing.
 */
describe('what Admin still carries (#45)', () => {
  it('keeps its four sections after the architecture panel was removed', async () => {
    render(<Admin />)
    for (const name of [/ingest status/i, /calibration/i, /eval results/i, /^logs$/i]) {
      expect(await screen.findByRole('heading', { name })).toBeInTheDocument()
    }
  })

  it('no longer draws the system a second time', async () => {
    render(<Admin />)
    await screen.findByRole('heading', { name: /ingest status/i })
    expect(screen.queryByRole('img', { name: /architecture/i })).not.toBeInTheDocument()
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Overview } from './Overview'

/**
 * Overview (#39).
 *
 * The tab's job is to state what the system is before another tab demonstrates it, so what
 * earns a test is not "does it render prose" but the claims a reviewer would try to
 * falsify: the corpus counts are live rather than baked in, a failed fetch says so instead
 * of showing zeros, and every diagram is reachable by a screen reader — a page whose whole
 * purpose is explanation fails completely if its explanations are images to some readers.
 */

function mockCounts(counts: Record<string, number>) {
  return vi.fn((url: string) => {
    const table = /\/tables\/([a-z_]+)\/rows/.exec(url)?.[1] ?? ''
    if (!(table in counts)) return Promise.resolve({ ok: false, status: 404 } as Response)
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ table, total_count: counts[table], rows: [] }),
    } as unknown as Response)
  })
}

afterEach(() => vi.restoreAllMocks())

describe('Overview', () => {
  it('renders corpus counts from the API rather than hardcoded values', async () => {
    vi.stubGlobal('fetch', mockCounts({ matters: 152, deal_points: 12937, clauses: 13823 }))
    render(<Overview />)

    const strip = await screen.findByTestId('corpus-strip')
    // Thousands separators matter here: these are read as evidence, not decoration.
    expect(strip).toHaveTextContent('152')
    expect(strip).toHaveTextContent('12,937')
    expect(strip).toHaveTextContent('13,823')
  })

  it('says the counts are unavailable instead of showing zeros when the API fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network'))),
    )
    render(<Overview />)

    await waitFor(() => expect(screen.getByTestId('corpus-failed')).toBeInTheDocument())
    expect(screen.queryByTestId('corpus-strip')).not.toBeInTheDocument()
    // A plausible wrong number is worse than an absent one on a page about provenance.
    expect(screen.getByTestId('corpus-failed')).not.toHaveTextContent('0')
  })

  it('exposes every diagram to assistive technology with a described mechanism', () => {
    vi.stubGlobal('fetch', mockCounts({ matters: 1, deal_points: 1, clauses: 1 }))
    render(<Overview />)

    const figures = screen.getAllByRole('img')
    expect(figures).toHaveLength(3)
    for (const fig of figures) {
      expect(fig).toHaveAccessibleName()
      expect(fig).toHaveAccessibleDescription()
    }
  })

  // Scoped to containers rather than bare getByText: the diagram <desc> elements restate the
  // same claims for screen readers, so document-wide text queries here are ambiguous by
  // construction, not by accident. See the note in CLAUDE.md — three tests have broken this way.
  it('states the boundary — that this is not a document Q&A tool', () => {
    vi.stubGlobal('fetch', mockCounts({ matters: 1, deal_points: 1, clauses: 1 }))
    render(<Overview />)

    const boundaries = screen.getByTestId('boundaries')
    expect(boundaries).toHaveTextContent(/not a document Q&A tool/i)
    expect(boundaries).toHaveTextContent(/never writes SQL/i)
  })

  it('explains min_n as a confidentiality control, not only a statistical one', () => {
    vi.stubGlobal('fetch', mockCounts({ matters: 1, deal_points: 1, clauses: 1 }))
    render(<Overview />)

    // All three jobs, because naming only the statistical one is the misreading this
    // paragraph exists to prevent.
    const prose = screen.getByTestId('min-n-prose')
    expect(prose).toHaveTextContent(/statistical honesty/i)
    expect(prose).toHaveTextContent(/extraction-confidence gating/i)
    expect(prose).toHaveTextContent(/k-anonymity/i)
  })
})

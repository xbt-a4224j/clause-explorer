import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import { App } from './App'
import { TABS } from './tabs'

/**
 * The shell is keyboard-first because the demo scripts are performed without touching a
 * mouse (docs/demo-scripts.md). If these fail, script 1 cannot be run as written.
 */

/**
 * Explore now renders inside the shell (#19) and calls /api/facets and /api/comparables, so
 * the shell's own tests have to answer those too — otherwise every shell test fails on an
 * unmocked fetch, which says nothing about the shell.
 */
function mockHealth(status = 'ok', cube = 'ok') {
  globalThis.fetch = vi.fn((url: string) => {
    if (String(url).includes('/healthz')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status, db: 'ok', cube, version: '0.1.0' }),
      })
    }
    if (String(url).includes('/facets')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            groups: [],
            total_n: 0,
            unfiltered_n: 0,
            corpus: { records: 0, facts: 0, categories: 0 },
          }),
      })
    }
    // Ask is tab two since #48, so pressing "2" mounts it and it reads the catalog
    if (String(url).includes('/agent/catalog')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ measures: [], dimensions: [], label_space: 0 }),
      })
    }
    if (String(url).includes('/agent/grading')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            cases: [],
            answerable_total: 0,
            answerable_correct: 0,
            refusal_total: 0,
            refusal_correct: 0,
            note: '',
          }),
      })
    }
    return Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          matters: [],
          candidate_count: 0,
          returned_count: 0,
          applied_filters: {
            folio_industry_code: null,
            folio_industry_label: null,
            rolled_up_to_descendants: 0,
            deal_size_band: null,
            signed_from: null,
            signed_to: null,
            ranked_by: 'matter id (no description given)',
          },
        }),
    })
  }) as unknown as typeof fetch
}

describe('shell', () => {
  beforeEach(() => mockHealth())

  it('renders the brand mark', () => {
    render(<App />)
    expect(screen.getByText('clause explorer')).toBeInTheDocument()
  })

  it('renders every registered tab', () => {
    render(<App />)
    for (const tab of TABS) {
      expect(screen.getByRole('tab', { name: new RegExp(tab.label, 'i') })).toBeInTheDocument()
    }
    // asserted against the constant rather than a literal: adding a tab is a product
    // decision, not a test failure, but a tab that renders no button is a bug
    expect(screen.getAllByRole('tab')).toHaveLength(TABS.length)
  })

  it('marks exactly one tab selected', () => {
    render(<App />)
    expect(screen.getAllByRole('tab', { selected: true })).toHaveLength(1)
  })

  it('opens Overview first — the frame before any view demonstrates it (#39)', () => {
    render(<App />)
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/overview/i)
  })

  it('puts Ask second — the act, not the mechanism, behind Overview (#48)', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('tab', { name: /^ask/i }))
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/^ask/i)
    // the old name described the implementation; nothing in the bar should still carry it
    expect(screen.queryByRole('tab', { name: /semantic layer/i })).not.toBeInTheDocument()
  })

  it('keeps Explore one key behind Ask — still the entry point for demo script 1', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('tab', { name: TABS[2].label }))
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/explore/i)
  })

  it('is six tabs — Coverage and Tables were cut (#48)', () => {
    render(<App />)
    expect(screen.getAllByRole('tab')).toHaveLength(6)
    expect(screen.queryByRole('tab', { name: /coverage/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /tables/i })).not.toBeInTheDocument()
  })
})

describe('stack health', () => {
  it('surfaces a degraded dependency rather than hiding it', async () => {
    mockHealth('degraded', 'unreachable')
    render(<App />)
    expect(await screen.findByText(/degraded/i)).toBeInTheDocument()
  })
})

/**
 * The header search box was decoration on five of six tabs.
 *
 * It rendered everywhere except Explore, `?` advertised "/ focus search", and it had no
 * handler at all: you could focus it, type into it, press Enter, and nothing happened. A
 * prominent control in the header that does nothing is worse than no control, because a
 * first-time user spends their first attempt on it.
 *
 * It carries what you typed to Explore now, which is where searching this corpus happens.
 */
describe('the header search goes somewhere', () => {
  beforeEach(() => mockHealth())

  it('takes what you typed to Explore', async () => {
    render(<App />)
    const search = screen.getByRole('searchbox', { name: 'search' })
    fireEvent.change(search, { target: { value: 'healthcare all cash' } })
    fireEvent.keyDown(search, { key: 'Enter' })

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /^Explore/ })).toHaveAttribute(
        'aria-selected',
        'true',
      ),
    )
    await waitFor(() =>
      expect(screen.getByLabelText('describe the deal')).toHaveValue('healthcare all cash'),
    )
  })

  it('does nothing on an empty box rather than jumping tabs', () => {
    render(<App />)
    const search = screen.getByRole('searchbox', { name: 'search' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(screen.getByRole('tab', { name: /^Overview/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('says where it goes, so the box is not a mystery', () => {
    render(<App />)
    expect(screen.getByRole('searchbox', { name: 'search' })).toHaveAttribute(
      'placeholder',
      expect.stringContaining('Explore'),
    )
  })
})

describe('a journey seed reaches Explore, not just the journey object', () => {
  /**
   * The gap that hid a real bug: Overview.test.tsx asserted on the SHAPE of `journey.seed`
   * without ever mounting Explore, so `journey.seed` could carry fields Explore's own
   * `seedFilters.filters` never reads and nothing would fail. This mounts the whole App, runs
   * the journey, switches to Explore, and reads the actual outgoing `/comparables` request --
   * the only way to prove the seed was APPLIED rather than merely well-typed.
   */
  it('applies the comparables journey seed to the real outgoing request', async () => {
    mockHealth()
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: /run this/i }))
    // the journey lands on Ask first (#47); the seed is consumed when Explore next mounts
    fireEvent.click(screen.getByRole('tab', { name: /explore/i }))

    await waitFor(() => {
      // The FIRST /comparables call fires before the seed effect applies (mount with empty
      // filters); the seeded request is a LATER call once `seedFilters` is consumed. Find the
      // one that actually carries the industry code rather than assuming position.
      const seeded = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (args: unknown[]) =>
          String(args[0]).includes('comparables') &&
          String((args[1] as RequestInit)?.body).includes('folio_industry_code'),
      )
      expect(seeded).toBeDefined()
      const body = JSON.parse(String((seeded![1] as RequestInit).body))
      expect(body.folio_industry_code).toBe('RCSG4k3ah1Pu5YgPexPgOmL')
      expect(body.consideration_type).toBe('All Cash')
    })
  })
})

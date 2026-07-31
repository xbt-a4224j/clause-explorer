import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
            corpus: { matters: 0, deal_points: 0, industries: 0 },
          }),
      })
    }
    if (String(url).includes('/coverage')) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            rows: [],
            columns: [],
            column_axis: 'year',
            column_note: '',
            column_totals: {},
            total_n: 0,
            min_n: 5,
            thin_cell_count: 0,
            empty_cell_count: 0,
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

  it('opens Explore first — the entry point for demo script 1', () => {
    render(<App />)
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/explore/i)
  })
})

describe('keyboard navigation', () => {
  beforeEach(() => mockHealth())

  it('switches tabs with number keys', async () => {
    render(<App />)
    await userEvent.keyboard('3')
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(
      new RegExp(TABS[2].label, 'i'),
    )
  })

  it('opens the shortcut overlay with ?', async () => {
    render(<App />)
    await userEvent.keyboard('?')
    expect(await screen.findByRole('dialog', { name: /shortcut/i })).toBeInTheDocument()
  })

  it('closes the overlay with Escape', async () => {
    render(<App />)
    await userEvent.keyboard('?')
    await screen.findByRole('dialog')
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('ignores shortcuts while typing in an input', async () => {
    render(<App />)
    const box = screen.getByRole('searchbox')
    await userEvent.type(box, '3')
    expect(box).toHaveValue('3')
    expect(screen.getByRole('tab', { selected: true })).toHaveAccessibleName(/explore/i)
  })

  it('focuses search with /', async () => {
    render(<App />)
    await userEvent.keyboard('/')
    expect(screen.getByRole('searchbox')).toHaveFocus()
  })
})

describe('stack health', () => {
  it('surfaces a degraded dependency rather than hiding it', async () => {
    mockHealth('degraded', 'unreachable')
    render(<App />)
    expect(await screen.findByText(/degraded/i)).toBeInTheDocument()
  })
})

import { render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DealTerms } from './DealTerms'
import type { DealTermsResponse } from '../types'

/**
 * Deal Terms (#21).
 *
 * The tab exists to replace a chart an associate builds by hand, so what is worth asserting is
 * the reporting discipline a hand-built chart usually loses: that a small sample never renders
 * as a percentage, that a deal point nobody negotiated stays visible, and that the copy does not
 * let the reader mistake public comparables for the firm's own history.
 */

const EIGHT = ['contract_1', 'contract_2', 'contract_3', 'contract_4', 'contract_5', 'contract_6', 'contract_7', 'contract_8']

const ROLLUP: DealTermsResponse = {
  selection_n: 8,
  percentage_threshold: 30,
  answered_deal_point_count: 2,
  absent_deal_point_count: 1,
  scope_note:
    'These are comparable PUBLIC deals from the MAUD study of SEC-filed merger agreements. ' +
    "This is not this firm's own matter history and must not be described as it.",
  rows: [
    {
      deal_point_name: 'Fiduciary exception to COR covenant',
      answered_n: 8,
      present_count: 6,
      display: '6 of 8',
      display_kind: 'count',
      positions: [
        { position: 'Yes', n: 6 },
        { position: 'No', n: 2 },
      ],
      numeric: null,
    },
    {
      deal_point_name: 'Ticking fee',
      answered_n: 8,
      present_count: 2,
      display: '2 of 8',
      display_kind: 'count',
      positions: [{ position: 'Yes', n: 2 }],
      numeric: { numeric_n: 2, median: 4, p25: 3, p75: 6.5 },
    },
    {
      deal_point_name: 'Go-shop period',
      answered_n: 0,
      present_count: 0,
      display: '0 of 8',
      display_kind: 'count',
      positions: [],
      numeric: null,
    },
  ],
}

function mockApi(body: unknown = ROLLUP, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => body }) as Response)
}

beforeEach(() => vi.stubGlobal('fetch', mockApi()))
afterEach(() => vi.unstubAllGlobals())

describe('the count-vs-percentage rule', () => {
  it('renders "6 of 8" and never a percentage below the threshold', async () => {
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Fiduciary exception to COR covenant')
    expect(within(row).getByText('6 of 8')).toBeInTheDocument()
    expect(row.textContent).not.toContain('%')
  })

  it('states the threshold that produced the rendering', async () => {
    render(<DealTerms selection={EIGHT} />)
    expect(await screen.findByText(/below n=30/i)).toBeInTheDocument()
  })
})

describe('absence is a finding', () => {
  it('shows a deal point nobody answered as a visible 0 row', async () => {
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Go-shop period')
    expect(within(row).getByText('0 of 8')).toBeInTheDocument()
  })
})

describe('numeric deal points', () => {
  it('shows median with p25/p75 and its own n', async () => {
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Ticking fee')
    // scoped to the numeric summary: the position breakdown also carries an n=2, and an
    // unscoped match would pass even if the median lost its own denominator
    const numeric = within(row).getByText(/median 4/)
    expect(numeric).toHaveTextContent('3–6.5')
    expect(numeric).toHaveTextContent('n=2')
  })

  it('shows no median for a non-numeric deal point', async () => {
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Fiduciary exception to COR covenant')
    expect(within(row).queryByText(/median/)).not.toBeInTheDocument()
  })
})

describe('scope', () => {
  it('says plainly that these are public comparables, not the firm’s own history', async () => {
    render(<DealTerms selection={EIGHT} />)
    expect(await screen.findByText(/comparable PUBLIC deals/i)).toBeInTheDocument()
    expect(screen.getByText(/not this firm's own matter history/i)).toBeInTheDocument()
  })
})

describe('designed states', () => {
  it('asks for a selection rather than rolling up the whole corpus', () => {
    render(<DealTerms selection={[]} />)
    expect(screen.getByText(/Select deals in Explore/i)).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows a skeleton while the rollup is in flight', () => {
    render(<DealTerms selection={EIGHT} />)
    expect(screen.getByLabelText('loading deal terms')).toBeInTheDocument()
  })

  it('reports a failed rollup distinctly from an empty one', async () => {
    vi.stubGlobal('fetch', mockApi({ error: { message: 'Cube did not answer' } }, false))
    render(<DealTerms selection={EIGHT} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/Cube did not answer/)
  })
})

import { fireEvent, render, screen, within } from '@testing-library/react'
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
  min_extraction_confidence: 0.7,
  refused: false,
  refusal: null,
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
      gate_note: null,
    },
    {
      deal_point_name: 'Ticking fee',
      answered_n: 8,
      present_count: 2,
      display: '2 of 8',
      display_kind: 'count',
      positions: [{ position: 'Yes', n: 2 }],
      numeric: { numeric_n: 2, median: 4, p25: 3, p75: 6.5 },
      gate_note: null,
    },
    {
      deal_point_name: 'Go-shop period',
      answered_n: 0,
      present_count: 0,
      display: '0 of 8',
      display_kind: 'count',
      positions: [],
      numeric: null,
      gate_note: null,
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

describe('drill-through', () => {
  const DRILL = {
    deal_point_name: 'Fiduciary exception to COR covenant',
    scope_note: ROLLUP.scope_note,
    matters: [
      {
        matter_id: 'contract_1',
        target_name: 'ACCELERON PHARMA INC.',
        position: 'Constructive knowledge',
        source_file: 'maud/data/contracts/contract_1.txt',
        source_span_start: 255704,
        source_span_end: 256033,
        clause_text: '“Knowledge” of Parent or the Company means the actual knowledge…',
        text_unavailable: null,
      },
      {
        matter_id: 'contract_2',
        target_name: 'ADAMAS PHARMACEUTICALS, INC.',
        position: 'Actual knowledge',
        source_file: 'maud/data/contracts/contract_2.txt',
        source_span_start: null,
        source_span_end: null,
        clause_text: null,
        text_unavailable: 'MAUD located no character range for this label.',
      },
    ],
  }

  function mockBoth() {
    return vi.fn(async (url: string) =>
      ({
        ok: true,
        json: async () => (String(url).includes('drill') ? DRILL : ROLLUP),
      }) as Response,
    )
  }

  it('shows the clause language, not just a list of matter ids', async () => {
    vi.stubGlobal('fetch', mockBoth())
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Fiduciary exception to COR covenant')
    fireEvent.click(within(row).getByRole('button', { name: /Fiduciary exception/ }))

    // demo script 2 beat 5: the actual clause language from the deals that have it
    expect(await within(row).findByText(/“Knowledge” of Parent or the Company/)).toBeInTheDocument()
  })

  it('shows the source file and character offsets behind each clause', async () => {
    vi.stubGlobal('fetch', mockBoth())
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Fiduciary exception to COR covenant')
    fireEvent.click(within(row).getByRole('button', { name: /Fiduciary exception/ }))

    const hit = await within(row).findByTestId('drill-contract_1')
    expect(hit).toHaveTextContent('maud/data/contracts/contract_1.txt')
    expect(hit).toHaveTextContent('255704')
    expect(hit).toHaveTextContent('256033')
  })

  it('says why a clause is missing rather than showing an empty quote', async () => {
    vi.stubGlobal('fetch', mockBoth())
    render(<DealTerms selection={EIGHT} />)
    const row = await screen.findByTestId('term-Fiduciary exception to COR covenant')
    fireEvent.click(within(row).getByRole('button', { name: /Fiduciary exception/ }))

    const hit = await within(row).findByTestId('drill-contract_2')
    expect(hit).toHaveTextContent(/located no character range/)
  })
})

describe('min_n refusal', () => {
  /**
   * #23: the most important behavior in the product. A selection below min_n must render its
   * own state — visually distinct from both "no terms found" and "the service is down".
   */
  const REFUSED = {
    selection_n: 2,
    percentage_threshold: 30,
    min_extraction_confidence: 0.7,
    answered_deal_point_count: 0,
    absent_deal_point_count: 0,
    scope_note: ROLLUP.scope_note,
    refused: true,
    refusal: {
      reason: 'insufficient_n',
      n: 2,
      threshold: 5,
      message: 'n=2 — insufficient to characterize (threshold 5)',
    },
    rows: [],
  }

  it('renders a distinct refusal state stating the actual n and the threshold', async () => {
    vi.stubGlobal('fetch', mockApi(REFUSED))
    render(<DealTerms selection={['contract_1', 'contract_2']} />)
    const refusal = await screen.findByTestId('refusal')
    expect(refusal).toHaveTextContent('n=2')
    expect(refusal).toHaveTextContent('threshold 5')
  })

  it('does not render the empty-result copy for a refusal', async () => {
    vi.stubGlobal('fetch', mockApi(REFUSED))
    render(<DealTerms selection={['contract_1', 'contract_2']} />)
    await screen.findByTestId('refusal')
    expect(screen.queryByText(/Select deals in Explore/i)).not.toBeInTheDocument()
  })

  it('does not render the refusal state for an ordinary error', async () => {
    vi.stubGlobal('fetch', mockApi({ error: { message: 'Cube did not answer' } }, false))
    render(<DealTerms selection={EIGHT} />)
    await screen.findByRole('alert')
    expect(screen.queryByTestId('refusal')).not.toBeInTheDocument()
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

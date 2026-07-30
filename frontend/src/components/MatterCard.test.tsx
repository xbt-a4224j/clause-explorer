import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MatterCard } from './MatterCard'
import type { Matter, MatterDetail } from '../types'

/**
 * The matter card (#20).
 *
 * The card is where inferred data and gold data sit side by side, so the assertions that earn
 * their place are the ones about telling them apart — and about the pasted paragraph, which
 * leaves the app and loses every visual cue the UI was using to qualify the numbers.
 */

const MATTER: Matter = {
  matter_id: 'contract_1',
  target_name: 'ACCELERON PHARMA INC.',
  acquirer_name: 'MERCK SHARP & DOHME CORP.',
  industry: 'Health Care Industry',
  is_inferred_industry: true,
  signing_date: '2021-09-29',
  score: 0.812,
  vector_score: 0.74,
  bm25_score: 0.88,
}

const DETAIL: MatterDetail = {
  matter_id: 'contract_1',
  target_name: 'ACCELERON PHARMA INC.',
  acquirer_name: 'MERCK SHARP & DOHME CORP.',
  industry: 'Health Care Industry',
  is_inferred_industry: true,
  signing_date: '2021-09-29',
  deal_value_usd: null,
  source_file: 'maud/data/contracts/contract_1.txt',
  source_contract_title: 'ACCELERON PHARMA INC. - Agreement and Plan of Merger',
  deal_point_count: 89,
  located_count: 80,
  summary:
    'MERCK SHARP & DOHME CORP. / ACCELERON PHARMA INC. — Health Care Industry (inferred from ' +
    'SIC, not an expert label), signed 2021-09-29. deal value not available. Negotiated terms ' +
    '(n=89, 80 traced to a source span): Fiduciary exception: Yes. Source: ACCELERON PHARMA ' +
    'INC. - Agreement and Plan of Merger (maud/data/contracts/contract_1.txt).',
  deal_points: [
    {
      deal_point_name: 'Fiduciary exception to COR covenant',
      position: 'Yes',
      is_inferred: false,
      numeric_value: null,
      source_span_start: 234875,
      source_span_end: 239289,
      clause_text: 'Notwithstanding anything to the contrary contained in this Agreement…',
      text_unavailable: null,
    },
    {
      deal_point_name: 'Ticking fee',
      position: 'No',
      is_inferred: false,
      numeric_value: null,
      source_span_start: null,
      source_span_end: null,
      clause_text: null,
      text_unavailable: 'MAUD located no character range for this label in the source agreement.',
    },
  ],
}

function mockDetail(overrides: Partial<MatterDetail> = {}) {
  return vi.fn(async () => ({ ok: true, json: async () => ({ ...DETAIL, ...overrides }) }) as Response)
}

function renderCard(props: Partial<Parameters<typeof MatterCard>[0]> = {}) {
  return render(
    <ul>
      <MatterCard
        matter={MATTER}
        focused={false}
        expanded={false}
        onFocus={() => {}}
        onToggle={() => {}}
        {...props}
      />
    </ul>,
  )
}

beforeEach(() => vi.stubGlobal('fetch', mockDetail()))
afterEach(() => vi.unstubAllGlobals())

describe('collapsed card', () => {
  it('flags an inferred industry', () => {
    renderCard()
    const card = screen.getByTestId('matter-contract_1')
    expect(within(card).getByText('inferred')).toBeInTheDocument()
  })

  it('does not flag a gold industry', () => {
    renderCard({ matter: { ...MATTER, is_inferred_industry: false } })
    const card = screen.getByTestId('matter-contract_1')
    expect(within(card).queryByText('inferred')).not.toBeInTheDocument()
  })
})

describe('drill-through', () => {
  it('lists the deal points with their positions once expanded', async () => {
    renderCard({ expanded: true })
    expect(await screen.findByText('Fiduciary exception to COR covenant')).toBeInTheDocument()
    expect(screen.getByText('Ticking fee')).toBeInTheDocument()
  })

  it('shows the source file and char offsets behind a located deal point', async () => {
    renderCard({ expanded: true })
    const dp = await screen.findByTestId('dp-Fiduciary exception to COR covenant')
    // the provenance rule: text must be traceable to a byte range in the downloaded source
    expect(within(dp).getByText(/maud\/data\/contracts\/contract_1\.txt/)).toBeInTheDocument()
    expect(within(dp).getByText(/234875/)).toBeInTheDocument()
    expect(within(dp).getByText(/239289/)).toBeInTheDocument()
  })

  it('renders the clause text for a located deal point', async () => {
    renderCard({ expanded: true })
    const dp = await screen.findByTestId('dp-Fiduciary exception to COR covenant')
    expect(within(dp).getByText(/Notwithstanding anything to the contrary/)).toBeInTheDocument()
  })

  it('says why there is no text rather than rendering an empty box', async () => {
    renderCard({ expanded: true })
    const dp = await screen.findByTestId('dp-Ticking fee')
    expect(within(dp).getByText(/located no character range/)).toBeInTheDocument()
  })

  it('reports how many deal points are traceable, with both numbers', async () => {
    renderCard({ expanded: true })
    expect(await screen.findByText(/80 of 89/)).toBeInTheDocument()
  })

  it('shows a designed loading state while the detail is in flight', () => {
    renderCard({ expanded: true })
    expect(screen.getByLabelText('loading deal points')).toBeInTheDocument()
  })

  it('reports a failed fetch instead of an empty deal-point list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        json: async () => ({ error: { code: 'not_found', message: 'No matter' } }),
      }) as Response),
    )
    renderCard({ expanded: true })
    expect(await screen.findByRole('alert')).toHaveTextContent(/No matter/)
  })
})

describe('copy summary', () => {
  it('copies a plain-text paragraph citing the source agreement', async () => {
    // typed param, not `async () => {}`: an argless mock types its calls as an empty tuple
    const writeText = vi.fn(async (_text: string) => {})
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    renderCard({ expanded: true })

    fireEvent.click(await screen.findByRole('button', { name: /Copy summary/ }))
    await waitFor(() => expect(writeText).toHaveBeenCalledOnce())

    const copied = writeText.mock.calls[0][0]
    expect(copied).toContain('ACCELERON PHARMA INC. - Agreement and Plan of Merger')
    // the badge does not survive a paste, so the word has to be in the text
    expect(copied.toLowerCase()).toContain('inferred')
    expect(copied).toContain('n=89')
    expect(copied).not.toContain('<')
  })
})

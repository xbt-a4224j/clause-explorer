import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRef } from 'react'
import { Explore } from './Explore'
import type { ComparablesResponse, FacetsResponse } from '../types'

/**
 * Explore (#19), against a mocked API.
 *
 * What is worth asserting here is the stuff that is invisible until it is wrong in front of a
 * partner: that counts carry their denominator, that a zero-count facet is disabled rather
 * than hidden, that j/k actually move, and that "no results" is visually distinct from "the
 * count service is down".
 */

const FACETS: FacetsResponse = {
  unfiltered_n: 152,
  total_n: 152,
  corpus: { matters: 152, deal_points: 12937, industries: 14 },
  groups: [
    {
      key: 'industry',
      label: 'Industry',
      total_n: 47,
      total_basis: 'matters in this slice with any industry resolved',
      inferred: true,
      values: [
        // the code travels with the label: /comparables filters by FOLIO code, and resolving a
        // label back to a code in the client is exactly the lookup #25 exists to prevent
        { value: 'Health Care Industry', code: 'RCSG4k3ah1Pu5YgPexPgOmL', n: 25, selected: false },
        { value: 'Manufacturing Industry', code: 'RBxLbTLwMitsqvA0VkYFxJf', n: 22, selected: false },
        { value: 'Educational Services Industry', code: 'REduPlaceholder00000001', n: 0, selected: false },
      ],
    },
    {
      key: 'year',
      label: 'Signing year',
      total_n: 149,
      total_basis: 'matters in this slice with a signing year',
      inferred: false,
      values: [
        { value: '2021', n: 116, selected: false },
        { value: '2020', n: 33, selected: false },
      ],
    },
  ],
}

const COMPARABLES: ComparablesResponse = {
  candidate_count: 25,
  returned_count: 2,
  applied_filters: {
    folio_industry_code: null,
    folio_industry_label: null,
    rolled_up_to_descendants: 0,
    deal_size_band: null,
    signed_from: null,
    signed_to: null,
    ranked_by: 'matter id (no description given)',
  },
  matters: [
    {
      matter_id: 'contract_1',
      target_name: 'ACCELERON PHARMA INC.',
      acquirer_name: 'MERCK SHARP & DOHME CORP.',
      industry: 'Health Care Industry',
      is_inferred_industry: true,
      signing_date: '2021-09-29',
      score: 0.812,
      vector_score: 0.74,
      bm25_score: 0.88,
    },
    {
      matter_id: 'contract_104',
      target_name: 'PPD, INC.',
      acquirer_name: 'THERMO FISHER SCIENTIFIC INC.',
      industry: 'Health Care Industry',
      is_inferred_industry: true,
      signing_date: '2021-04-15',
      score: 0.66,
      vector_score: 0.6,
      bm25_score: 0.71,
    },
  ],
}

// expanding a card fetches its detail (#20); the list must keep working regardless
const MATTER_DETAIL = {
  matter_id: 'contract_1',
  target_name: 'ACCELERON PHARMA INC.',
  acquirer_name: 'MERCK SHARP & DOHME CORP.',
  industry: 'Health Care Industry',
  is_inferred_industry: true,
  signing_date: '2021-09-29',
  deal_value_usd: null,
  source_file: 'maud/data/contracts/contract_1.txt',
  source_contract_title: 'ACCELERON PHARMA INC. - Agreement and Plan of Merger',
  deal_point_count: 1,
  located_count: 1,
  summary: 'summary (n=1)',
  deal_points: [
    {
      deal_point_name: 'Fiduciary exception to COR covenant',
      position: 'Yes',
      is_inferred: false,
      numeric_value: null,
      source_span_start: 1,
      source_span_end: 2,
      clause_text: 'x',
      text_unavailable: null,
    },
  ],
}

function mockApi(overrides: { facets?: unknown; comparables?: unknown; fail?: boolean } = {}) {
  return vi.fn(async (url: string, _init?: RequestInit) => {
    if (overrides.fail) {
      return {
        ok: false,
        json: async () => ({ error: { code: 'unavailable', message: 'Cube did not answer' } }),
      } as Response
    }
    const body = url.includes('facets')
      ? (overrides.facets ?? FACETS)
      : url.includes('/matters/')
        ? MATTER_DETAIL
        : (overrides.comparables ?? COMPARABLES)
    return { ok: true, json: async () => body } as Response
  })
}

function renderExplore() {
  const ref = createRef<HTMLInputElement>()
  return render(<Explore searchRef={ref as React.MutableRefObject<HTMLInputElement | null>} />)
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockApi())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('facet rail', () => {
  it('shows a count with its denominator for every facet value', async () => {
    renderExplore()
    // scoped to the rail: "Health Care Industry" also appears on the matter cards, and an
    // unscoped query matches both
    const rail = await screen.findByLabelText('filters')
    const healthCare = await within(rail).findByRole('button', { name: /Health Care Industry/ })
    expect(within(healthCare).getByText('n=25')).toBeInTheDocument()
  })

  it('renders a zero-count value disabled rather than hiding it', async () => {
    renderExplore()
    const empty = await screen.findByRole('button', { name: /Educational Services/ })
    expect(empty).toBeDisabled()
    expect(within(empty).getByText('n=0')).toBeInTheDocument()
  })

  it('renders a group with no filterable values disabled, with its reason', async () => {
    // deal size has no data until #9 lands. Dropping the group would claim the corpus has no
    // size axis at all; showing it enabled would offer a filter that cannot narrow anything.
    vi.stubGlobal(
      'fetch',
      mockApi({
        facets: {
          ...FACETS,
          groups: [
            ...FACETS.groups,
            {
              key: 'band',
              label: 'Deal size',
              total_n: 152,
              unavailable: 'Deal size is not filterable: no deal values have been enriched yet.',
              values: [{ value: 'unknown', n: 152, selected: false }],
            },
          ],
        },
      }),
    )
    renderExplore()
    const group = await screen.findByTestId('facet-band')
    expect(within(group).getByText(/no deal values have been enriched yet/)).toBeInTheDocument()
    expect(within(group).getByRole('button', { name: /unknown/ })).toBeDisabled()
  })

  it('reports the selected total against the unfiltered total', async () => {
    renderExplore()
    expect(await screen.findByText(/of 152 matters/)).toBeInTheDocument()
  })
})

describe('filter before rank', () => {
  /**
   * #18's whole point: the filter runs in Postgres and the hybrid index is built over exactly
   * the surviving matters, so scores are relative to the requested slice. If Explore filters
   * the *response* in the browser instead, two things break silently — the partner sees
   * "showing 3 of 25" where 25 counted matters they never asked about, and the ranking they
   * are reading was normalized against that wider corpus.
   */
  it('sends the selected industry to /comparables as a FOLIO code', async () => {
    const fetchMock = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    renderExplore()

    const rail = await screen.findByLabelText('filters')
    // #38: the rail's landmark renders before its facets arrive, so a synchronous getByRole
    // here raced the response. Wait for the button, not for its container.
    fireEvent.click(await within(rail).findByRole('button', { name: /Health Care Industry/ }))

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).includes('comparables') &&
          JSON.parse(String((init as RequestInit).body)).folio_industry_code != null,
      )
      expect(call).toBeDefined()
      expect(JSON.parse(String((call![1] as RequestInit).body)).folio_industry_code).toBe(
        'RCSG4k3ah1Pu5YgPexPgOmL',
      )
    })
  })

  it('does not re-filter the ranked response in the browser', async () => {
    // the server is the authority on what is in the slice. If Explore drops rows the server
    // returned, the count and the ranking disagree with each other.
    vi.stubGlobal(
      'fetch',
      mockApi({
        comparables: {
          ...COMPARABLES,
          matters: [
            COMPARABLES.matters[0],
            { ...COMPARABLES.matters[1], industry: 'Manufacturing Industry' },
          ],
        },
      }),
    )
    renderExplore()
    const rail = await screen.findByLabelText('filters')
    // #38: the rail's landmark renders before its facets arrive, so a synchronous getByRole
    // here raced the response. Wait for the button, not for its container.
    fireEvent.click(await within(rail).findByRole('button', { name: /Health Care Industry/ }))

    await waitFor(() => expect(screen.getByTestId('matter-contract_104')).toBeInTheDocument())
  })
})

describe('coverage pre-filter', () => {
  /** A Coverage cell click hands Explore a code and year (#22) — this is the receiving end. */
  it('applies seed filters from a Coverage cell click and consumes them', async () => {
    const onConsumed = vi.fn()
    const ref = createRef<HTMLInputElement>()
    render(
      <Explore
        searchRef={ref as React.MutableRefObject<HTMLInputElement | null>}
        seedFilters={{
          folio_industry_code: 'RCSG4k3ah1Pu5YgPexPgOmL',
          folio_industry_label: 'Health Care Industry',
          signing_year: '2020',
          consideration_type: null,
        }}
        onSeedConsumed={onConsumed}
      />,
    )
    await waitFor(() => expect(onConsumed).toHaveBeenCalledOnce())
  })
})

describe('results', () => {
  it('shows a loading skeleton before data arrives, not a blank panel', () => {
    renderExplore()
    expect(screen.getByLabelText('loading results')).toBeInTheDocument()
  })

  it('renders matter cards with the inferred-industry flag', async () => {
    renderExplore()
    const card = await screen.findByTestId('matter-contract_1')
    expect(within(card).getByText('ACCELERON PHARMA INC.')).toBeInTheDocument()
    expect(within(card).getByText('inferred')).toBeInTheDocument()
  })

  it('shows the resolved query above the answer', async () => {
    renderExplore()
    const resolved = await screen.findByTestId('resolved-query')
    expect(resolved.textContent).toContain('n=25')
  })
})

describe('keyboard', () => {
  it('j and k move the focused result', async () => {
    renderExplore()
    const first = await screen.findByTestId('matter-contract_1')
    expect(first).toHaveAttribute('aria-current', 'true')

    fireEvent.keyDown(window, { key: 'j' })
    await waitFor(() =>
      expect(screen.getByTestId('matter-contract_104')).toHaveAttribute('aria-current', 'true'),
    )

    fireEvent.keyDown(window, { key: 'k' })
    await waitFor(() =>
      expect(screen.getByTestId('matter-contract_1')).toHaveAttribute('aria-current', 'true'),
    )
  })

  it('k at the top of the list does not wrap or crash', async () => {
    renderExplore()
    await screen.findByTestId('matter-contract_1')
    fireEvent.keyDown(window, { key: 'k' })
    expect(screen.getByTestId('matter-contract_1')).toHaveAttribute('aria-current', 'true')
  })

  it('Enter expands the focused result', async () => {
    renderExplore()
    await screen.findByTestId('matter-contract_1')
    fireEvent.keyDown(window, { key: 'Enter' })
    expect(await screen.findByText('bm25')).toBeInTheDocument()
  })

  it('does not steal keys while typing in the description box', async () => {
    renderExplore()
    // await the list first: the search input renders during loading, so resolving on it alone
    // asserts nothing about the cursor — there are no cards yet to move between
    await screen.findByTestId('matter-contract_1')
    const input = screen.getByLabelText('describe the deal')
    fireEvent.keyDown(input, { key: 'j' })
    expect(screen.getByTestId('matter-contract_1')).toHaveAttribute('aria-current', 'true')
    expect(screen.getByTestId('matter-contract_104')).not.toHaveAttribute('aria-current', 'true')
  })
})

describe('designed states', () => {
  it('an empty result says which filters produced it and offers to clear', async () => {
    vi.stubGlobal(
      'fetch',
      mockApi({ comparables: { ...COMPARABLES, matters: [], candidate_count: 0 } }),
    )
    renderExplore()
    expect(await screen.findByText(/No comparable deals in this slice/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Clear filters/ })).toBeInTheDocument()
  })

  it('a failed semantic layer is distinct from an empty result', async () => {
    vi.stubGlobal('fetch', mockApi({ fail: true }))
    renderExplore()
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Counts unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/No comparable deals in this slice/)).not.toBeInTheDocument()
  })
})

describe('provenance at the point of display (#35)', () => {
  it('names the corpus behind each headline count', async () => {
    render(<Explore searchRef={{ current: null }} onSelectionChange={() => {}} />)
    const corpus = await screen.findByText(/matters ·/)
    expect(corpus).toHaveTextContent(/MAUD/)
    expect(corpus).toHaveTextContent(/FOLIO/)
  })

  it('says the industry figure is inferred, beside the figure', async () => {
    render(<Explore searchRef={{ current: null }} onSelectionChange={() => {}} />)
    const corpus = await screen.findByText(/matters ·/)
    expect(corpus).toHaveTextContent(/inferred/)
  })

  it('states the corpus date range so nobody says "the last five years"', async () => {
    render(<Explore searchRef={{ current: null }} onSelectionChange={() => {}} />)
    expect(await screen.findByText(/2020-03-13 to\s+2021-11-21/)).toBeInTheDocument()
  })
})

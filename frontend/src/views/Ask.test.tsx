import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Ask } from './Ask'
import type { CatalogResponse } from '../types'

/**
 * Ask (#36; renamed from Semantic Layer and moved second in the bar by #48).
 *
 * The tab exists to make one argument inspectable: the model selects from a fixed
 * vocabulary, so correctness is discrete and gradeable, and the number itself is computed
 * by Postgres rather than produced by the model.
 *
 * What earns a test is therefore not "does it render" but the three claims a reviewer would
 * try to falsify: the vocabulary is live rather than checked in, the selection is shown
 * separately from the number it produced, and the tab is honest that a *wrong selection*
 * still returns a real number.
 */

const CATALOG: CatalogResponse = {
  label_space: 3,
  measures: [
    {
      name: 'deal_points.n',
      title: 'N',
      type: 'count',
      cube: 'deal_points',
      description: 'matters answering this deal point',
    },
    {
      name: 'deal_points.median_numeric_value',
      title: 'Median',
      type: 'number',
      cube: 'deal_points',
      description: 'percentile_cont(0.5) WITHIN GROUP, never avg',
    },
  ],
  dimensions: [
    {
      name: 'matters.industry_code',
      title: 'Industry',
      type: 'string',
      cube: 'matters',
      description: 'industry code, not the display label',
    },
  ],
}

const GRADING = {
  cases: [
    {
      id: 'q01',
      question: 'how many matters are there in total',
      should_refuse: false,
      expected_measures: ['deal_points.matters_total'],
      actual_measures: ['deal_points.count_distinct_matters'],
      expected_dimensions: [],
      actual_dimensions: [],
      correct: false,
    },
  ],
  answerable_total: 20,
  answerable_correct: 13,
  refusal_total: 5,
  refusal_correct: 1,
  note: 'Graded from committed fixtures with no database and no model call.',
}

/** Routes by URL: the tab now calls three endpoints, and answering all of them with the
 *  catalog made unrelated assertions fail for reasons that had nothing to do with them. */
function mockCatalog(body: unknown = CATALOG, status = 200) {
  const fetchMock = vi.fn(async (url: string) => {
    if (String(url).includes('/grading')) {
      return { ok: true, status: 200, json: async () => GRADING } as Response
    }
    return { ok: status < 400, status, json: async () => body } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('the vocabulary', () => {
  it('lists the measures and dimensions the model may select from', async () => {
    mockCatalog()
    render(<Ask />)
    const catalog = await screen.findByTestId('catalog')
    expect(within(catalog).getByText('deal_points.median_numeric_value')).toBeInTheDocument()
    expect(within(catalog).getByText('matters.industry_code')).toBeInTheDocument()
  })

  it('shows each entry description — an opaque identifier cannot be reviewed', async () => {
    mockCatalog()
    render(<Ask />)
    // scoped: percentile_cont also appears in the freeform-SQL contrast block by design
    const catalog = await screen.findByTestId('catalog')
    expect(within(catalog).getByText(/percentile_cont/)).toBeInTheDocument()
  })

  it('states the label space size, because that is the gradeability claim', async () => {
    mockCatalog()
    render(<Ask />)
    await waitFor(() => expect(screen.getByTestId('label-space')).toHaveTextContent('3'))
  })

  it('separates measures from dimensions', async () => {
    mockCatalog()
    render(<Ask />)
    const measures = await screen.findByTestId('catalog-measures')
    expect(within(measures).queryByText('matters.industry_code')).not.toBeInTheDocument()
  })
})

describe('the argument sits below the demonstration (#48)', () => {
  it('renders the explainer after the catalog and the builder, not in front of them', async () => {
    mockCatalog()
    render(<Ask />)
    const builder = await screen.findByTestId('query-builder')
    const explainer = screen.getByRole('button', { name: /what the semantic layer is for/i })
    // renaming the tab to Ask demotes the argument; it is not weakened, it moves
    expect(builder.compareDocumentPosition(explainer) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })

  it('keeps the governed-vocabulary argument verbatim', async () => {
    mockCatalog()
    render(<Ask />)
    await screen.findByTestId('query-builder')
    const prose = document.querySelector('.explain__prose')!
    expect(prose).toHaveTextContent(/router.*not a calculator/i)
    expect(prose).toHaveTextContent(/picks a measure and filters from the published vocabulary/i)
  })
})

describe('honesty about what the layer does not fix', () => {
  it('says a wrong selection still returns a real number', async () => {
    mockCatalog()
    render(<Ask />)
    const caveat = await screen.findByTestId('relocated-risk')
    expect(caveat).toHaveTextContent(/wrong question|real number/i)
  })

  it('explains that the freeform arm is not executed', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('freeform-note')).toHaveTextContent(/not (run|executed)/i)
  })
})

describe('designed states', () => {
  it('reports an unreachable semantic layer rather than an empty vocabulary', async () => {
    mockCatalog({ detail: 'Cube did not return its metadata' }, 503)
    render(<Ask />)
    expect(await screen.findByRole('heading', { name: /unavailable/i })).toBeInTheDocument()
    expect(screen.queryByTestId('catalog')).not.toBeInTheDocument()
  })

  it('renders the vocabulary with no API key — only live selection needs one', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('catalog')).toBeInTheDocument()
    expect(screen.getByTestId('keyless-note')).toBeInTheDocument()
  })
})

/**
 * #37 — the builder. The claim it makes is structural: there is no way to express an invalid
 * measure, because there is no free-text input. That absence is what earns a test, along with
 * the query pane matching what would actually be sent.
 */
describe('the query builder', () => {
  it('offers no free-text input at all — that absence is the argument', async () => {
    mockCatalog()
    render(<Ask />)
    const qb = await screen.findByTestId('query-builder')
    expect(within(qb).queryByRole('textbox')).not.toBeInTheDocument()
    expect(qb.querySelectorAll('input, textarea')).toHaveLength(0)
  })

  it('builds the query from clicks, and shows exactly what it will send', async () => {
    mockCatalog()
    render(<Ask />)
    const qb = await screen.findByTestId('query-builder')

    fireEvent.click(within(qb).getByRole('button', { name: /median_numeric_value/ }))
    await waitFor(() =>
      expect(screen.getByTestId('qb-query')).toHaveTextContent('deal_points.median_numeric_value'),
    )
  })

  it('will not run without a measure — there is nothing to compute', async () => {
    mockCatalog()
    render(<Ask />)
    const qb = await screen.findByTestId('query-builder')
    expect(within(qb).getByRole('button', { name: /run against postgres/i })).toBeDisabled()
  })

  it('renders a refusal distinctly from an empty result', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/grading')) {
        return { ok: true, status: 200, json: async () => GRADING } as Response
      }
      if (String(url).includes('run-selection')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            query: {},
            rows: [],
            n: 3,
            refused: true,
            threshold: 5,
            message: 'n=3 — insufficient to characterize (threshold 5).',
          }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => CATALOG } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Ask />)
    const qb = await screen.findByTestId('query-builder')

    fireEvent.click(within(qb).getByRole('button', { name: /^n deal_points$/ }))
    fireEvent.click(within(qb).getByRole('button', { name: /run against postgres/i }))

    const refused = await screen.findByTestId('qb-refused')
    expect(refused).toHaveTextContent(/insufficient/i)
    expect(refused).toHaveTextContent('3')
    expect(screen.queryByTestId('qb-rows')).not.toBeInTheDocument()
  })
})

describe('worked examples (#37)', () => {
  it('offers examples to start from — 56 names with no entry point is a reference card', async () => {
    mockCatalog()
    render(<Ask />)
    const ex = await screen.findByTestId('qb-examples')
    expect(ex.querySelectorAll('button').length).toBeGreaterThanOrEqual(3)
  })

  it('loading one fills the builder and explains it in English', async () => {
    mockCatalog()
    render(<Ask />)
    const ex = await screen.findByTestId('qb-examples')

    fireEvent.click(within(ex).getByText(/COVID-19 by name/i))

    expect(screen.getByTestId('qb-note')).toHaveTextContent(/lawyer gave|carve-out/i)
    expect(screen.getByTestId('qb-query')).toHaveTextContent('deal_points.present_count')
    expect(screen.getByTestId('qb-filters')).toBeInTheDocument()
  })

  it('includes one that is meant to be refused', async () => {
    mockCatalog()
    render(<Ask />)
    const ex = await screen.findByTestId('qb-examples')
    expect(within(ex).getByText(/single company/i)).toBeInTheDocument()
  })

  it('says why Run is disabled rather than leaving a dead button', async () => {
    mockCatalog()
    render(<Ask />)
    const qb = await screen.findByTestId('query-builder')
    expect(qb).toHaveTextContent(/also need a measure/i)
  })
})

describe('inline jargon (#35)', () => {
  it('defines its own terms without leaving the tab', async () => {
    mockCatalog()
    render(<Ask />)
    await screen.findByTestId('query-builder')
    // the explainer prose carries clickable terms; clicking one reveals a definition in place
    const terms = document.querySelectorAll('.term__btn')
    expect(terms.length).toBeGreaterThan(0)
  })
})

/**
 * #47/#50 — the free-text path is on the tab, and its cost accumulates at the foot of it.
 *
 * The component tests cover the chips and the formatting; what is only checkable here is the
 * wiring: asking a question through the box moves the tab's running total.
 */
describe('the question box and its running cost', () => {
  const ASK_RESPONSE = {
    question: 'healthcare deals',
    measures: ['comparable_deals.n'],
    dimensions: [],
    filters: [],
    time_dimensions: [],
    model_selection: { measures: ['comparable_deals.n'], dimensions: [], filters: [], timeDimensions: [] },
    runnable: true,
    blocked_reason: null,
    usage: {
      model: 'gpt-4o-mini',
      prompt_tokens: 726,
      completion_tokens: 64,
      latency_ms: 2734,
      cost_usd: 0.0001473,
      price_checked_on: '2026-09-03',
      price_source: 'https://developers.openai.com/api/docs/pricing',
    },
  }

  function mockWithAsk() {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/grading')) {
        return { ok: true, status: 200, json: async () => GRADING } as Response
      }
      if (String(url).includes('/agent/ask')) {
        return { ok: true, status: 200, json: async () => ASK_RESPONSE } as Response
      }
      return { ok: true, status: 200, json: async () => CATALOG } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  }

  it('puts a free-text box on the tab — until #47 there was none', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('ask-question')).toBeInTheDocument()
  })

  it('shows no session total before anything is asked', async () => {
    mockCatalog()
    render(<Ask />)
    await screen.findByTestId('query-builder')
    expect(screen.queryByTestId('ask-session')).not.toBeInTheDocument()
  })

  it('accumulates the measured cost at the foot of the tab once a question is asked', async () => {
    mockWithAsk()
    render(<Ask />)
    const box = await screen.findByTestId('ask-question')
    fireEvent.change(box, { target: { value: 'healthcare deals' } })
    fireEvent.click(screen.getByRole('button', { name: /interpret/i }))

    const total = await screen.findByTestId('ask-session')
    expect(total).toHaveTextContent('1 question')
    expect(total).toHaveTextContent('$0.000147')
  })
})

describe('the offline grade (#36)', () => {
  it('shows the grade computed from committed fixtures', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('grade-answerable')).toHaveTextContent('13 of 20')
  })

  it('reports refusal accuracy separately rather than averaging it away', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('grade-refusal')).toHaveTextContent('1 of 5')
  })

  it('states the bad refusal number as the finding, not a footnote', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('grade-finding')).toHaveTextContent(/min_n|enforced in the API/i)
  })

  it('shows the freeform arm for contrast, marked as not run', async () => {
    mockCatalog()
    render(<Ask />)
    expect(await screen.findByTestId('freeform-note')).toHaveTextContent(/not run/i)
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SemanticLayer } from './SemanticLayer'
import type { CatalogResponse } from '../types'

/**
 * Semantic Layer (#36).
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
      name: 'matters.folio_industry_code',
      title: 'Industry',
      type: 'string',
      cube: 'matters',
      description: 'FOLIO code, not the display label',
    },
  ],
}

function mockCatalog(body: unknown = CATALOG, status = 200) {
  const fetchMock = vi.fn(
    async () => ({ ok: status < 400, status, json: async () => body }) as Response,
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('the vocabulary', () => {
  it('lists the measures and dimensions the model may select from', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    const catalog = await screen.findByTestId('catalog')
    expect(within(catalog).getByText('deal_points.median_numeric_value')).toBeInTheDocument()
    expect(within(catalog).getByText('matters.folio_industry_code')).toBeInTheDocument()
  })

  it('shows each entry description — an opaque identifier cannot be reviewed', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    expect(await screen.findByText(/percentile_cont/)).toBeInTheDocument()
  })

  it('states the label space size, because that is the gradeability claim', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    await waitFor(() => expect(screen.getByTestId('label-space')).toHaveTextContent('3'))
  })

  it('separates measures from dimensions', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    const measures = await screen.findByTestId('catalog-measures')
    expect(within(measures).queryByText('matters.folio_industry_code')).not.toBeInTheDocument()
  })
})

describe('honesty about what the layer does not fix', () => {
  it('says a wrong selection still returns a real number', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    const caveat = await screen.findByTestId('relocated-risk')
    expect(caveat).toHaveTextContent(/wrong question|real number/i)
  })

  it('explains that the freeform arm is not executed', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    expect(await screen.findByTestId('freeform-note')).toHaveTextContent(/not (run|executed)/i)
  })
})

describe('designed states', () => {
  it('reports an unreachable semantic layer rather than an empty vocabulary', async () => {
    mockCatalog({ detail: 'Cube did not return its metadata' }, 503)
    render(<SemanticLayer />)
    expect(await screen.findByRole('heading', { name: /unavailable/i })).toBeInTheDocument()
    expect(screen.queryByTestId('catalog')).not.toBeInTheDocument()
  })

  it('renders the vocabulary with no API key — only live selection needs one', async () => {
    mockCatalog()
    render(<SemanticLayer />)
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
    render(<SemanticLayer />)
    const qb = await screen.findByTestId('query-builder')
    expect(within(qb).queryByRole('textbox')).not.toBeInTheDocument()
    expect(qb.querySelectorAll('input, textarea')).toHaveLength(0)
  })

  it('builds the query from clicks, and shows exactly what it will send', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    const qb = await screen.findByTestId('query-builder')

    fireEvent.click(within(qb).getByRole('button', { name: /median_numeric_value/ }))
    await waitFor(() =>
      expect(screen.getByTestId('qb-query')).toHaveTextContent('deal_points.median_numeric_value'),
    )
  })

  it('will not run without a measure — there is nothing to compute', async () => {
    mockCatalog()
    render(<SemanticLayer />)
    const qb = await screen.findByTestId('query-builder')
    expect(within(qb).getByRole('button', { name: /run against postgres/i })).toBeDisabled()
  })

  it('renders a refusal distinctly from an empty result', async () => {
    const fetchMock = vi.fn(async (url: string) => {
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
    render(<SemanticLayer />)
    const qb = await screen.findByTestId('query-builder')

    fireEvent.click(within(qb).getByRole('button', { name: /^n deal_points$/ }))
    fireEvent.click(within(qb).getByRole('button', { name: /run against postgres/i }))

    const refused = await screen.findByTestId('qb-refused')
    expect(refused).toHaveTextContent(/insufficient/i)
    expect(refused).toHaveTextContent('3')
    expect(screen.queryByTestId('qb-rows')).not.toBeInTheDocument()
  })
})

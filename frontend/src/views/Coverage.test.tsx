import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Coverage } from './Coverage'
import type { CoverageResponse } from '../types'

/**
 * Coverage (#22).
 *
 * The design inversion is the point: default BI styling emphasises the big numbers, but a gap
 * is more actionable than a strength already known. So what earns a test here is that thinness
 * is loud rather than faded, that the boundary is exact, and that a click carries a FOLIO code
 * to Explore rather than a display label.
 */

const GRID: CoverageResponse = {
  columns: ['2020', '2021'],
  column_axis: 'year',
  column_note: 'Columns are signing year. Deal size is the intended axis but has no data.',
  column_totals: { '2020': 24, '2021': 42 },
  total_n: 66,
  min_n: 5,
  thin_cell_count: 1,
  empty_cell_count: 0,
  rows: [
    {
      label: 'Health Care Industry',
      folio_industry_code: 'RCSG4k3ah1Pu5YgPexPgOmL',
      total_n: 25,
      cells: [
        { column: '2020', n: 6, reportable: true, note: null, folio_industry_code: 'RCSG4k3ah1Pu5YgPexPgOmL' },
        { column: '2021', n: 19, reportable: true, note: null, folio_industry_code: 'RCSG4k3ah1Pu5YgPexPgOmL' },
      ],
    },
    {
      label: 'Manufacturing Industry',
      folio_industry_code: 'RBOjgvcq6Z33XxMhTxWiiDS',
      total_n: 22,
      cells: [
        {
          column: '2020',
          n: 18,
          reportable: true,
          note: null,
          folio_industry_code: 'RBOjgvcq6Z33XxMhTxWiiDS',
        },
        {
          column: '2021',
          n: 4,
          reportable: false,
          note: 'n=4 — insufficient to characterize (threshold 5)',
          folio_industry_code: 'RBOjgvcq6Z33XxMhTxWiiDS',
        },
      ],
    },
  ],
}

function mockApi(body: unknown = GRID, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => body }) as Response)
}

beforeEach(() => vi.stubGlobal('fetch', mockApi()))
afterEach(() => vi.unstubAllGlobals())

describe('the grid', () => {
  it('renders rows by industry and columns by the chosen axis', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    expect(await screen.findByText('Health Care Industry')).toBeInTheDocument()
    expect(screen.getByText('Manufacturing Industry')).toBeInTheDocument()
    const headers = screen.getAllByRole('columnheader')
    expect(headers.map((h) => h.textContent)).toEqual(expect.arrayContaining(['2020', '2021']))
  })

  it('shows every count with its cell', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    const cell = await screen.findByTestId('cell-Health Care Industry-2020')
    expect(cell).toHaveTextContent('6')
  })
})

describe('thin cells are loud, not faded', () => {
  it('marks a below-threshold cell distinctly, not with reduced emphasis', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    const thin = await screen.findByTestId('cell-Manufacturing Industry-2021')
    // prominence, not fading: a visible marker class rather than opacity/greyed styling
    expect(thin.className).toContain('cov__cell--thin')
    expect(thin).not.toHaveClass('cov__cell--faded')
  })

  it('states the threshold and the actual n on a thin cell', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    const thin = await screen.findByTestId('cell-Manufacturing Industry-2021')
    expect(thin).toHaveTextContent('insufficient to characterize')
    expect(thin).toHaveTextContent('4')
  })

  it('renders a cell at exactly min_n as ordinary, not thin', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    const boundary = await screen.findByTestId('cell-Health Care Industry-2020')
    expect(boundary.className).not.toContain('cov__cell--thin')
  })

  it('reports the total count of thin and empty cells', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    expect(await screen.findByText(/1 of 4 cells below n=5/)).toBeInTheDocument()
  })
})

describe('totals', () => {
  it('shows a row total for every row', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    const row = await screen.findByTestId('cov-row-Health Care Industry')
    expect(within(row).getByText('25')).toBeInTheDocument()
  })

  it('shows a column total for every column', async () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    const totals = await screen.findByTestId('cov-column-totals')
    expect(within(totals).getByText('24')).toBeInTheDocument()
    expect(within(totals).getByText('42')).toBeInTheDocument()
  })
})

describe('click to pre-filtered Explore', () => {
  it('navigates with the FOLIO code behind the cell, not the display label', async () => {
    const onNav = vi.fn()
    render(<Coverage onNavigateToExplore={onNav} />)
    const cell = await screen.findByTestId('cell-Health Care Industry-2020')
    fireEvent.click(within(cell).getByRole('button'))
    expect(onNav).toHaveBeenCalledWith({
      folio_industry_code: 'RCSG4k3ah1Pu5YgPexPgOmL',
      folio_industry_label: 'Health Care Industry',
      signing_year: '2020',
    })
  })
})

describe('designed states', () => {
  it('shows a loading skeleton before the grid arrives', () => {
    render(<Coverage onNavigateToExplore={() => {}} />)
    expect(screen.getByLabelText('loading coverage grid')).toBeInTheDocument()
  })

  it('reports a failed grid distinctly from an empty one', async () => {
    vi.stubGlobal('fetch', mockApi({ error: { message: 'Cube did not answer' } }, false))
    render(<Coverage onNavigateToExplore={() => {}} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/Cube did not answer/)
  })
})

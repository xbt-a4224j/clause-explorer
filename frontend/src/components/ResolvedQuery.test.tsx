import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ResolvedQuery } from './ResolvedQuery'
import type { AgentSelection } from '../types'

/**
 * ResolvedQuery (#26).
 *
 * The risk of an agent misreading a question doesn't vanish when the selection is
 * enum-constrained — it relocates: a wrong but valid selection returns a real number for the
 * wrong question. This line is what lets the one person qualified to catch that actually catch
 * it, so every component of the selection has to be visible, in plain language, including the
 * denominator and which parts were resolved or inferred rather than typed verbatim.
 */

const SELECTION: AgentSelection = {
  measures: ['deal_points.median_numeric_value'],
  dimensions: [],
  filters: [
    {
      member: 'comparable_deals.label',
      operator: 'equals',
      values: ['Health Care Industry'],
      raw: 'healthcare',
      resolved: true,
      inferred: false,
    },
    {
      member: 'comparable_deals.deal_size_band',
      operator: 'equals',
      values: ['mid-market'],
      raw: 'mid-market',
      resolved: false,
      inferred: false,
    },
  ],
  timeDimensions: [{ dimension: 'comparable_deals.signing_year', range: '2020 to 2025' }],
  n: 8,
  is_inferred: true,
}

describe('every component renders', () => {
  it('shows the measure, filters, time range, and n', () => {
    render(<ResolvedQuery selection={SELECTION} onEdit={() => {}} />)
    const line = screen.getByTestId('resolved-query')
    expect(line).toHaveTextContent('median_numeric_value')
    expect(line).toHaveTextContent('Health Care Industry')
    expect(line).toHaveTextContent('mid-market')
    expect(line).toHaveTextContent('2020 to 2025')
    expect(line).toHaveTextContent('n=8')
  })
})

describe('resolved values are shown, not raw user text', () => {
  it('shows what the raw text resolved to, not the raw text alone', () => {
    render(<ResolvedQuery selection={SELECTION} onEdit={() => {}} />)
    const filter = screen.getByTestId('resolved-filter-comparable_deals.label')
    expect(filter).toHaveTextContent('healthcare')
    expect(filter).toHaveTextContent('Health Care Industry')
    expect(within(filter).getByText('→')).toBeInTheDocument()
  })

  it('does not show a resolution arrow for a filter that needed no resolution', () => {
    render(<ResolvedQuery selection={SELECTION} onEdit={() => {}} />)
    const filter = screen.getByTestId('resolved-filter-comparable_deals.deal_size_band')
    expect(within(filter).queryByText('→')).not.toBeInTheDocument()
  })
})

describe('inferred dimensions are flagged', () => {
  it('flags the query as touching inferred data', () => {
    render(<ResolvedQuery selection={SELECTION} onEdit={() => {}} />)
    expect(screen.getByTestId('resolved-query')).toHaveTextContent('inferred')
  })

  it('does not flag a query with no inferred dimension', () => {
    render(
      <ResolvedQuery selection={{ ...SELECTION, is_inferred: false }} onEdit={() => {}} />,
    )
    expect(screen.getByTestId('resolved-query')).not.toHaveTextContent('inferred')
  })
})

describe('edit affordance', () => {
  it('opens the selection for manual correction', () => {
    const onEdit = vi.fn()
    render(<ResolvedQuery selection={SELECTION} onEdit={onEdit} />)
    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    expect(onEdit).toHaveBeenCalledWith(SELECTION)
  })
})

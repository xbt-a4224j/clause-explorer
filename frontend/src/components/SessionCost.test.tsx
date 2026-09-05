import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SessionCost } from './SessionCost'

/**
 * #50 — the running total at the foot of the tab.
 *
 * One question priced at a fraction of a cent is not an argument about cost; several of them
 * accumulating in front of the reader is. The total is summed from the same measured `usage`
 * payloads the per-question line renders, so the two can never disagree.
 */
describe('the session total', () => {
  it('renders nothing before a question is asked — an empty total is noise', () => {
    const { container } = render(<SessionCost questions={0} costUsd={0} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('carries the count alongside the dollars, never a bare figure', () => {
    render(<SessionCost questions={3} costUsd={0.0004419} />)
    const total = screen.getByTestId('ask-session')
    expect(total).toHaveTextContent('3 questions')
    expect(total).toHaveTextContent('$0.000442')
  })

  it('says "1 question", not "1 questions"', () => {
    render(<SessionCost questions={1} costUsd={0.0001473} />)
    expect(screen.getByTestId('ask-session')).toHaveTextContent('1 question ')
  })
})

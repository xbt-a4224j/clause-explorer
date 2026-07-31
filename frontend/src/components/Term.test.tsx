import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { GLOSSARY, Term } from './Term'

/**
 * #35 — jargon was unlearnable from the app. What earns a test is that a term is defined
 * without leaving the screen, and that the glossary covers the words the product actually
 * uses rather than a convenient subset.
 */
describe('inline glossary', () => {
  it('defines a term in place, without navigating away', () => {
    render(<Term>MAUD</Term>)
    fireEvent.click(screen.getByRole('button', { name: 'MAUD' }))
    expect(screen.getByRole('note')).toHaveTextContent(/Merger Agreement Understanding Dataset/)
  })

  it('renders unknown words unchanged rather than swallowing them', () => {
    render(<Term>not a term</Term>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('not a term')).toBeInTheDocument()
  })

  it('covers every term the product puts in front of a user', () => {
    for (const t of [
      'MAUD',
      'CUAD',
      'FOLIO',
      'EDGAR',
      'deal point',
      'public target',
      'fiduciary out',
      'reverse termination fee',
      'min_n',
      'k-anonymity',
      'inferred',
    ]) {
      expect(GLOSSARY[t], `${t} is used in the UI but undefined`).toBeDefined()
    }
  })

  it('every definition states what it is before elaborating', () => {
    for (const [term, e] of Object.entries(GLOSSARY)) {
      expect(e.short.length, `${term} short`).toBeGreaterThan(8)
      expect(e.long.length, `${term} long`).toBeGreaterThan(40)
    }
  })
})

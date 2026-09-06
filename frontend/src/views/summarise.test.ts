import { describe, expect, it } from 'vitest'
import { summarise } from './Ask'

/**
 * The Cube descriptions are written AT THE MODEL — they open with a shouted flag and run for a
 * paragraph. Rendering them whole made the vocabulary panel a wall of 29 paragraphs; rendering
 * a naive "first sentence" mangled four of them. These are the four.
 */
describe('summarise', () => {
  it('lifts a shouted label out as a tag rather than discarding it', () => {
    const { role, lead } = summarise(
      'THE DENOMINATOR. The number of labelled matters in the current selection.',
    )
    expect(role).toBe('THE DENOMINATOR')
    expect(lead).toBe('The number of labelled matters in the current selection.')
  })

  it('accepts a label terminated by an em dash', () => {
    // rendered inline as "THE DENOMINATOR FOR EVERY PERCENTILE BELOW — how many answers..."
    const { role, lead } = summarise(
      'THE DENOMINATOR FOR EVERY PERCENTILE BELOW — how many answers carry a number at all. 809 of 12,937 rows.',
    )
    expect(role).toBe('THE DENOMINATOR FOR EVERY PERCENTILE BELOW')
    expect(lead).toBe('How many answers carry a number at all.')
  })

  it('does not read a single capitalised word as a label', () => {
    // `FALSE for MAUD's expert labels` is prose; tagging FALSE said the opposite of the text
    const { role, lead } = summarise("FALSE for MAUD's expert labels, TRUE for anything extracted.")
    expect(role).toBeNull()
    expect(lead).toBe("FALSE for MAUD's expert labels, TRUE for anything extracted.")
  })

  it('does not treat e.g. as the end of a sentence', () => {
    // truncated to "The ABA deal point being answered, e.g." before this
    const { lead } = summarise(
      'The ABA deal point being answered, e.g. "Type of Consideration-Answer". 92 distinct values.',
    )
    expect(lead).toContain('Type of Consideration')
    expect(lead).not.toContain('92 distinct')
  })

  it('leaves an identifier lower-case', () => {
    // blanket capitalising turned this into `Percentile_cont(0.5)`
    const { lead } = summarise('percentile_cont(0.5) WITHIN GROUP, never avg')
    expect(lead).toBe('percentile_cont(0.5) WITHIN GROUP, never avg')
  })

  it('survives an empty description', () => {
    expect(summarise('')).toEqual({ role: null, lead: '' })
  })
})

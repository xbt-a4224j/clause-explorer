import type { TabId } from './tabs'

/**
 * The three journeys the product exists to serve, as data.
 *
 * Overview used to end with a paragraph naming all eight tabs, which told a reader what the
 * tabs were called and not what anyone would do with them. These are the same three walkthroughs
 * `docs/demo-scripts.md` treats as the acceptance test, made runnable: each carries the filters
 * its first step needs, so "run this" lands on a filtered view rather than an empty one.
 *
 * Each journey names a person, because the three have genuinely different readers — the analyst
 * assembling comparables, the associate checking a claim, and the data manager deciding whether
 * an extractor may run on firm documents — and a tool that serves all three without saying so
 * reads as a feature list.
 */

export interface JourneySeed {
  folio_industry_code: string | null
  folio_industry_label: string | null
  signing_year: string | null
  consideration_type: string | null
}

export interface Journey {
  id: string
  /** who walks in with this question */
  who: string
  /** the question, in the words they would use */
  question: string
  /** what they do today, and why it is expensive */
  today: string
  /** the clicks, in order — rendered as the card's diagram */
  steps: readonly string[]
  /** what they leave with */
  outcome: string
  /** an honest note about what this journey cannot do yet, or null */
  limit: string | null
  /** where "run this" lands */
  tab: TabId
  /** filters applied on arrival, when the journey starts from a filtered set */
  seed: JourneySeed | null
  cta: string
}

/** FOLIO code for Health Care Industry, joined on rather than matched by label (#18). */
const HEALTH_CARE = 'RCSG4k3ah1Pu5YgPexPgOmL'

export const JOURNEYS: readonly Journey[] = [
  {
    id: 'comparables',
    who: 'A knowledge-management analyst',
    question:
      '“Partner is pitching a healthcare target tomorrow, all cash. What did boards get on fiduciary outs?”',
    today:
      'Search the document system by keyword, open eight agreements, read each no-shop section, build a table by hand.',
    steps: [
      'Explore · healthcare, all cash',
      'Deal Terms · roll the set up',
      'open the outliers',
      'the clause, in the filing',
    ],
    outcome: 'Counts with their denominator, and the two deals that went the other way.',
    limit: null,
    tab: 'explore',
    seed: {
      folio_industry_code: HEALTH_CARE,
      folio_industry_label: 'Health Care Industry',
      signing_year: null,
      consideration_type: 'All Cash',
    },
    cta: 'Run this',
  },
  {
    id: 'is-it-market',
    who: 'An associate',
    question: '“A partner said everyone is doing commercially reasonable efforts now. Is that true?”',
    today: 'Trust the recollection, or spend an afternoon proving it and still hedge the answer.',
    steps: [
      'Deal Terms · the whole set',
      'read the distribution',
      'narrow the slice',
      'the gate refuses a thin one',
    ],
    outcome: 'A base rate, and an explicit statement of what this sample cannot support.',
    limit: null,
    tab: 'deal-terms',
    seed: null,
    cta: 'Open Deal Terms',
  },
  {
    id: 'trust-the-extractor',
    who: 'A data manager',
    question: '“Before this runs over our own precedents, where is the extractor weak?”',
    today: 'Take the vendor’s accuracy claim, or annotate a sample by hand to check it.',
    steps: [
      'Admin · accuracy per deal point',
      'Label · disagreements first',
      'decide, by keyboard',
      'a per-deal-point go or no-go',
    ],
    outcome: 'Which questions the extractor may answer on un-annotated documents, and which it must decline.',
    limit:
      'Half built. Decisions are recorded; calibration does not read them back yet, so the accuracy table does not move.',
    tab: 'admin',
    seed: null,
    cta: 'Open Admin',
  },
] as const

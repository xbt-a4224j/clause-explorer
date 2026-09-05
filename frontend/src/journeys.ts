import type { TabId } from './tabs'

/**
 * The two journeys the product exists to serve, as data.
 *
 * Overview used to end with a paragraph naming all eight tabs, which told a reader what the
 * tabs were called and not what anyone would do with them. These are walkthroughs from
 * `docs/demo-scripts.md`, made runnable: each carries the filters its Explore step needs, so
 * "run this" ends on a filtered view rather than an empty one.
 *
 * #48 cut the third. "Is that really market?" was the Coverage-adjacent one — its payoff was
 * the gate refusing a thin slice, which is the same argument the first journey makes when it
 * rolls up a set, and three journeys for three different readers is a suite rather than a
 * product. Each remaining journey names a person: the analyst assembling comparables, and the
 * data manager deciding whether an extractor may run on firm documents.
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
      'the clause, in the filing',
    ],
    outcome: 'Counts with their denominator, and the two deals that went the other way.',
    limit: null,
    // The journey begins where the question is put, but Ask has no free-text box until #47
    // lands one. Until then "Run this" goes to Explore, where every step is performable; #47
    // moves it to 'ask' in the same commit that gives Ask something to type into.
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
    id: 'trust-the-extractor',
    who: 'A data manager',
    question: '“Before this runs over our own precedents, where is the extractor weak?”',
    today: 'Take the vendor’s accuracy claim, or annotate a sample by hand to check it.',
    steps: [
      'Admin · accuracy per deal point',
      'Label · disagreements first',
      'accept, correct, edit or skip',
      'Label · the panel says it went down',
    ],
    outcome:
      'Which questions the extractor may answer on un-annotated documents, and which it must decline — with the reviewer’s decisions graded into that number rather than filed away.',
    limit: null,
    tab: 'admin',
    seed: null,
    cta: 'Open Admin',
  },
] as const

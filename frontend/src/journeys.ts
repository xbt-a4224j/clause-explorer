import type { JourneySeed } from '@semantic-explorer-base/ui'
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

/**
 * `JourneySeed` is the platform's own type now (`{filters?, description?}`, keyed by whatever
 * a domain's own facet groups are called) — this file used to redeclare it with clause-
 * explorer's field names as top-level properties (`folio_industry_code`, `signing_year`, ...)
 * rather than nested under `filters`. That shape was never what Explore's `seedFilters` prop
 * actually reads (`seedFilters.filters ?? {}`), so `App.tsx`'s `setSeed(journey.seed)`
 * type-checked — every field here is optional on the real type, so the excess properties were
 * silently tolerated — while doing nothing at runtime: Explore always saw `filters: undefined`
 * and applied no filters at all. No test caught it because the only journey test asserts the
 * shape of `journey.seed` itself, not that Explore ever receives it. Found and fixed while
 * genericising Explore's own filter keys for a second domain (semantic-explorer-base's Explore
 * fix, 2026-09-07) — the two bugs are unrelated, but touching this file's seed shape to keep
 * pace with Explore's new group-key convention (`industry`/`industry_code`/`consideration`
 * rather than `folio_industry_label`/`consideration_type`) is what surfaced this one.
 */

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
    who: 'A KM lawyer',
    // "all cash" was in this question and it made the journey unperformable: consideration type
    // is a deal-point ANSWER, not a record-level slice, so asking for fiduciary outs sliced by it
    // is two deal points at once — outside the four shapes, and the app correctly declines. It
    // enters at the Explore step below, where it is a real filter. The question now asks what Ask
    // can actually answer.
    question:
      '“Partner is pitching a healthcare target tomorrow. What did boards get on fiduciary outs?”',
    today:
      'Search the DMS by keyword, open eight precedents, read each no-shop section, build a table by hand.',
    steps: [
      'Ask · the measure and the slice',
      'Explore · healthcare, all cash',
      'Deal Terms · roll the set up',
      'the clause, in the filing',
    ],
    outcome: 'Counts with their denominator, and the two deals that went the other way.',
    limit: null,
    // #47 landed the free-text box, so the journey now starts where the question is actually
    // put. It used to drop the reader on Explore because step one could not be performed on
    // Ask — an honest workaround for a missing feature, and stale the moment the feature
    // arrived. The seed still travels: the Explore step arrives already narrowed.
    tab: 'ask',
    seed: {
      filters: {
        industry: 'Health Care Industry',
        industry_code: HEALTH_CARE,
        consideration: 'All Cash',
      },
    },
    cta: 'Run this',
  },
  {
    id: 'trust-the-extractor',
    who: 'The engineer evaluating the extractor',
    question: '“Before this runs over our own precedents, where is the extractor weak?”',
    today: 'Take the vendor’s accuracy claim, or annotate a sample by hand to check it.',
    steps: [
      'Trust · accuracy per deal point',
      'Label · disagreements first',
      'accept, correct, edit or skip',
      'Label · the panel says it went down',
    ],
    outcome:
      'Which questions the extractor may answer on un-annotated documents, and which it must decline — with the reviewer’s decisions graded into that number rather than filed away.',
    limit: null,
    tab: 'trust',
    seed: null,
    cta: 'Open Trust',
  },
] as const

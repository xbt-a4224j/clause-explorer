import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRef } from 'react'
import { Admin } from './views/Admin'
import { Ask } from './views/Ask'
import { DealTerms } from './views/DealTerms'
import { Explore } from './views/Explore'
import { Label } from './views/Label'
import { Overview } from './views/Overview'
import { Grading } from './components/Grading'
import { MatterCard } from './components/MatterCard'
import { QueryBuilder } from './components/QueryBuilder'
import type { Matter } from './types'

/**
 * #38 — unmounting a view must abort its in-flight requests.
 *
 * The `cancelled` boolean these views used stopped the `setState` but let the request run to
 * completion: the socket stayed open, the JSON was still parsed, and under a parallel test
 * runner the resolution still landed after cleanup. An `AbortController` ends the request
 * itself, which is both the real fix and the only one observable from outside the component.
 *
 * What is asserted is deliberately structural: every `fetch` receives a signal, and after
 * unmount every signal handed out is aborted. A stubbed `fetch` cannot demonstrate a cancelled
 * socket, so asserting on the signal is the strongest available evidence that the abort is
 * wired rather than declared.
 */

function recordingFetch(body: unknown = {}) {
  const signals: (AbortSignal | undefined)[] = []
  const fn = vi.fn(async (_url: string, init?: RequestInit) => {
    signals.push(init?.signal ?? undefined)
    return { ok: true, json: async () => body } as Response
  })
  return { fn, signals }
}

/** Bodies shaped enough for each view to render; the assertion is about the signal. */
const BODIES: Record<string, unknown> = {
  rows: [],
  columns: [],
  items: [],
  lines: [],
  measures: [],
  dimensions: [],
  matters: [],
  deal_points: [],
  total_count: 0,
  total_matched: 0,
  labelled_count: 0,
  queue_size: 0,
  applied_filters: { ranked_by: 'test' },
  candidate_count: 0,
  facets: {},
}

const MATTER: Matter = {
  matter_id: 'm-1',
  target_name: 'TARGET INC',
  acquirer_name: 'ACQUIRER CORP',
  signing_date: '2021-01-01',
  folio_industry_label: 'Health Care Industry',
  folio_industry_code: 'RCSG4k3ah1Pu5YgPexPgOmL',
  deal_value_usd: null,
  deal_size_band: null,
  consideration_type: null,
  score: 1,
  why: [],
  is_inferred_industry: true,
} as unknown as Matter

let recorder: ReturnType<typeof recordingFetch>

beforeEach(() => {
  recorder = recordingFetch(BODIES)
  vi.stubGlobal('fetch', recorder.fn)
})
afterEach(() => vi.unstubAllGlobals())

function expectAbortedOnUnmount(unmount: () => void) {
  expect(recorder.fn).toHaveBeenCalled()
  expect(recorder.signals.every((s) => s !== undefined)).toBe(true)
  unmount()
  for (const signal of recorder.signals) {
    expect(signal?.aborted).toBe(true)
  }
}

describe('every fetching view aborts on unmount', () => {
  it('DealTerms', () => {
    expectAbortedOnUnmount(render(<DealTerms selection={['m-1']} />).unmount)
  })

  it('Explore', () => {
    const searchRef = createRef<HTMLInputElement>()
    expectAbortedOnUnmount(render(<Explore searchRef={searchRef} />).unmount)
  })

  it('Label', () => {
    expectAbortedOnUnmount(render(<Label />).unmount)
  })

  it('Admin', () => {
    expectAbortedOnUnmount(render(<Admin />).unmount)
  })

  it('Ask', () => {
    expectAbortedOnUnmount(render(<Ask />).unmount)
  })

  it('Overview', () => {
    expectAbortedOnUnmount(render(<Overview onStartJourney={() => {}} />).unmount)
  })

  it('Grading', () => {
    expectAbortedOnUnmount(render(<Grading />).unmount)
  })

  it('MatterCard, once expanded', () => {
    expectAbortedOnUnmount(
      render(
        <MatterCard
          matter={MATTER}
          focused={false}
          expanded
          onFocus={() => {}}
          onToggle={() => {}}
        />,
      ).unmount,
    )
  })
})

describe('QueryBuilder — the one component with no cancel handling at all', () => {
  it('aborts a running query when the panel unmounts', () => {
    const { unmount } = render(
      <QueryBuilder
        measures={[
          {
            name: 'deal_points.n',
            title: 'n',
            type: 'number',
            cube: 'deal_points',
            description: 'count',
          },
        ]}
        dimensions={[]}
      />,
    )
    // select a measure so the run button is enabled, then start a query
    fireEvent.click(screen.getByRole('button', { name: 'n deal_points' }))
    fireEvent.click(screen.getByRole('button', { name: /Run against Postgres/ }))
    expectAbortedOnUnmount(unmount)
  })
})

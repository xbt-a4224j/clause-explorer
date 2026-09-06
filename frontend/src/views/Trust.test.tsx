import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Trust } from './Trust'
import { TABS } from '../tabs'

/**
 * Trust (#54) — the tab that replaced Admin.
 *
 * What earns a test here is not "does a chart render" but the honesty properties, because
 * those are the ones a refactor silently breaks:
 *
 * - the two unmeasurable deal points render "not measured", never 0.00
 * - the copy says the label loop **lowered** the score (the same guard #52 put on Label)
 * - refusal accuracy is labelled as the weak one with no alarm styling
 * - every chart has a table view and a hover layer
 * - nothing is recomputed: the figures are whatever the committed artefact says
 */

const CALIBRATION = {
  markdown: '# calibration',
  min_extraction_confidence: 0.7,
  vocabulary_size: 92,
  measured_deal_point_count: 90,
  reportable_count: 5,
  cost: {
    call_count: 1701,
    total_tokens: 5504632,
    cost_usd: 0.854442,
    prompt_tokens: 5440750,
    completion_tokens: 63882,
  },
  results: [
    {
      deal_point_name: 'Definition includes stock deals-Answer',
      n: 19,
      correct: 0,
      accuracy: 0.0,
      ci_low: 0.0,
      ci_high: 0.168,
      reportable: false,
      measured: true,
    },
    {
      deal_point_name: 'Fiduciary exception: Board determination trigger (no shop)-Answer',
      n: 20,
      correct: 16,
      accuracy: 0.8,
      ci_low: 0.584,
      ci_high: 0.919,
      reportable: false,
      measured: true,
    },
    {
      deal_point_name: 'Actions required under transaction agreement-Answer (Y/N)',
      n: 20,
      correct: 19,
      accuracy: 0.95,
      ci_low: 0.764,
      ci_high: 0.991,
      reportable: true,
      measured: true,
    },
    {
      deal_point_name: 'Absence of Litigation Closing Condition: Governmental v. Non-Governmental',
      n: 0,
      correct: 0,
      accuracy: null,
      ci_low: null,
      ci_high: null,
      reportable: false,
      measured: false,
    },
  ],
}

const LABELS = {
  generated_at: '2026-09-04T03:12:58+00:00',
  command: 'PYTHONPATH=backend python -m explorer.evals.calibration',
  prediction_count: 1701,
  labels_applied: 6,
  labels_differing: 5,
  correct_before: 569,
  correct_after: 565,
  accuracy_before: 0.335,
  accuracy_after: 0.332,
  min_extraction_confidence: 0.7,
  results: [],
}

const SELECTION = {
  generated_at: '2026-09-05T20:00:00+00:00',
  command: 'PYTHONPATH=backend python -m explorer.evals --only measure-selection',
  case_count: 25,
  answerable_count: 20,
  refusal_count: 5,
  measure_precision: 0.8,
  measure_recall: 0.775,
  dimension_precision: 0.692,
  dimension_recall: 0.725,
  filter_exact_match_rate: 0.5,
  refusal_accuracy: 0.2,
}

/** `overrides.labels` lets a test drive the zero state without a second mock. */
function mockApi(overrides: { labels?: typeof LABELS } = {}) {
  const labels = overrides.labels ?? LABELS
  const fetchMock = vi.fn(async (url: string) => {
    const u = String(url)
    // calibration-labels must be matched before calibration — its path is a superstring
    if (u.includes('calibration-labels')) {
      return { ok: true, status: 200, json: async () => labels } as Response
    }
    if (u.includes('measure-selection')) {
      return { ok: true, status: 200, json: async () => SELECTION } as Response
    }
    if (u.includes('calibration')) {
      return { ok: true, status: 200, json: async () => CALIBRATION } as Response
    }
    return { ok: true, status: 200, json: async () => ({ runs: [], lines: [], total_matched: 0 }) } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('the tab bar', () => {
  it('carries Trust and no longer carries Admin, still six tabs', () => {
    expect(TABS).toHaveLength(6)
    expect(TABS.map((t) => t.id)).toContain('trust')
    expect(TABS.map((t) => t.id)).not.toContain('admin')
  })

  it('positions Trust after Deal Terms', () => {
    const ids = TABS.map((t) => t.id)
    expect(ids.indexOf('trust')).toBe(ids.indexOf('deal-terms') + 1)
  })
})

describe('accuracy across the deal-point vocabulary', () => {
  it('draws one bar row per deal point, measured or not', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-accuracy-bars')
    expect(within(chart).getAllByTestId('trust-accuracy-bars-row')).toHaveLength(4)
  })

  it('renders an unmeasured deal point as "not measured", never as 0.00', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-accuracy-bars')
    expect(within(chart).getByText('not measured')).toBeInTheDocument()
  })

  it('draws the gate as a labelled rule rather than a colour change', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-accuracy-bars')
    expect(within(chart).getByText('0.70 gate')).toBeInTheDocument()
    expect(chart.querySelector('.viz__rule')).toBeInTheDocument()
  })

  it('separates the point-estimate count from the gate the product enforces', async () => {
    mockApi()
    render(<Trust />)
    // The caption used to say "5 of 90 ... 77 below the gate", two different populations in one
    // sentence, so the numbers did not add up and a reader could not tell what was measured.
    // The three buckets have to reconcile to the total, and the confidence argument sits below.
    const frame = await screen.findByTestId('trust-accuracy')
    expect(frame).toHaveTextContent(/split three ways/i)
    expect(frame).toHaveTextContent(/lower end of the confidence interval/i)
  })

  it('gives every bar a hover layer carrying its interval and n', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-accuracy-bars')
    expect(chart.querySelectorAll('title').length).toBeGreaterThan(0)
    expect(chart.textContent).toMatch(/95% CI/)
  })
})

describe('every chart has a table view behind a toggle', () => {
  for (const testId of [
    'trust-accuracy',
    'trust-disagreement',
    'trust-selection',
  ]) {
    it(`${testId} toggles to a table`, async () => {
      mockApi()
      render(<Trust />)
      const frame = await screen.findByTestId(testId)
      expect(within(frame).queryByTestId(`${testId}-table`)).not.toBeInTheDocument()
      fireEvent.click(within(frame).getByRole('button', { name: 'table' }))
      expect(within(frame).getByTestId(`${testId}-table`)).toBeInTheDocument()
    })
  }
})

describe('the copy states direction', () => {
  it('never claims the label loop improved anything', async () => {
    mockApi()
    render(<Trust />)
    await screen.findByTestId('trust-loop-direction')
    // the same guard #52 put on the Label panel
    expect(document.body.textContent ?? '').not.toMatch(/improved|better|▲|↑/)
  })

  it('says the score went down, with both numbers', async () => {
    mockApi()
    render(<Trust />)
    const line = await screen.findByTestId('trust-loop-direction')
    expect(line).toHaveTextContent(/went down/i)
    expect(line).toHaveTextContent('569')
    expect(line).toHaveTextContent('565')
  })

  it('keeps the corpus caveat on the loop visual', async () => {
    mockApi()
    render(<Trust />)
    expect(await screen.findByTestId('trust-corpus-caveat')).toHaveTextContent(
      /already has a lawyer|gold label/i,
    )
  })
})

describe('where the reviewer disagreed', () => {
  it('stacks the outcomes with a 2px surface gap and a legend', async () => {
    mockApi()
    render(<Trust />)
    const bar = await screen.findByTestId('trust-disagreement-bar')
    expect(within(bar).getAllByTestId('trust-disagreement-bar-seg')).toHaveLength(2)
    const frame = screen.getByTestId('trust-disagreement')
    expect(frame.querySelectorAll('.viz__legend li')).toHaveLength(2)
  })

  it('splits the differing decisions by what they cost, from the data', async () => {
    // The fixture has 6 decisions, 5 differing, and 4 that overwrote a correct answer
    // (569 → 565). The note must derive that split rather than assert a remembered finding:
    // the live table was purged of its development keystrokes and now holds none.
    mockApi()
    render(<Trust />)
    const frame = await screen.findByTestId('trust-disagreement')
    expect(frame).toHaveTextContent(/5 differed from the model/i)
    expect(frame).toHaveTextContent(/4 overwrote an answer that had been correct/i)
    expect(frame).toHaveTextContent(/1 swapped one wrong answer for another/i)
  })

  it('says nothing has been reviewed when the table is empty, and claims no finding', async () => {
    mockApi({ labels: { ...LABELS, labels_applied: 0, labels_differing: 0, correct_after: 569 } })
    render(<Trust />)
    const frame = await screen.findByTestId('trust-disagreement')
    expect(frame).toHaveTextContent(/nothing has been reviewed yet/i)
    // an empty table must not produce a finding about human review
    expect(frame.textContent ?? '').not.toMatch(/none of them was right|differed from the model/i)
  })

  it('never reports the loop as an improvement, in either state', async () => {
    mockApi({ labels: { ...LABELS, labels_applied: 0, labels_differing: 0, correct_after: 569 } })
    render(<Trust />)
    const direction = await screen.findByTestId('trust-loop-direction')
    expect(direction.textContent ?? '').not.toMatch(/improved|better|▲|↑/)
    expect(direction).toHaveTextContent(/no decisions recorded yet/i)
  })

  it('keeps the empty bucket in the table rather than drawing a zero-width segment', async () => {
    mockApi()
    render(<Trust />)
    const frame = await screen.findByTestId('trust-disagreement')
    fireEvent.click(within(frame).getByRole('button', { name: 'table' }))
    const table = within(frame).getByTestId('trust-disagreement-table')
    expect(table).toHaveTextContent('reviewer corrected a wrong model answer')
  })
})

describe('selection quality', () => {
  it('charts the four things the model is scored on', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-selection-bars')
    expect(within(chart).getAllByTestId('trust-selection-bars-row')).toHaveLength(4)
  })

  it('direct-labels refusal accuracy as the weak one', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-selection-bars')
    expect(within(chart).getByText(/the weak one/i)).toBeInTheDocument()
  })

  it('uses no alarm styling for it — a measurement, not an incident', async () => {
    mockApi()
    render(<Trust />)
    const frame = await screen.findByTestId('trust-selection')
    // No alarm class, and no red painted inline. Deliberately NOT matching the bare word
    // "red" against the markup — "authored", "lowered", "differed" and "measured" all contain
    // it, and a test that fails on honest prose is worse than no test.
    expect(frame.querySelector('.is-bad, .admin__bad, .qb__refused, .grade__row--bad')).toBeNull()
    expect(frame.innerHTML).not.toMatch(/#e34948|#d7263d|#c00|crimson|firebrick/i)
    // the weak bar wears the same mark class as every other bar — one series, one hue
    const bars = frame.querySelectorAll('.viz__bar')
    expect(bars).toHaveLength(4)
    expect([...bars].every((b) => b.getAttribute('style') === null)).toBe(true)
  })

  it('labels selectively — three of the four bars carry no number', async () => {
    mockApi()
    render(<Trust />)
    const chart = await screen.findByTestId('trust-selection-bars')
    expect(chart.querySelectorAll('.viz__value')).toHaveLength(1)
  })
})

describe('cost is a stat-tile row, not a chart', () => {
  it('renders calls, dollars and tokens both ways', async () => {
    mockApi()
    render(<Trust />)
    const tiles = await screen.findByTestId('trust-cost')
    expect(tiles).toHaveTextContent('1,701')
    expect(tiles).toHaveTextContent('$0.854442')
    expect(tiles).toHaveTextContent('5,440,750')
    expect(tiles).toHaveTextContent('63,882')
  })
})

describe('Trust absorbs Admin', () => {
  it('hides the operator surface behind a disclosure', async () => {
    mockApi()
    render(<Trust />)
    const toggle = await screen.findByTestId('trust-operator-toggle')
    expect(screen.queryByTestId('trust-operator')).not.toBeInTheDocument()
    fireEvent.click(toggle)
    expect(screen.getByTestId('trust-operator')).toBeInTheDocument()
  })

  it('still carries ingest status and the log viewer once opened', async () => {
    mockApi()
    render(<Trust />)
    fireEvent.click(await screen.findByTestId('trust-operator-toggle'))
    const operator = screen.getByTestId('trust-operator')
    expect(within(operator).getByText('Ingest status')).toBeInTheDocument()
    expect(within(operator).getByText('Logs')).toBeInTheDocument()
  })
})

/**
 * The zero state, now that the `labels` table is genuinely empty.
 *
 * The prose around the loop was rewritten to derive from the data, and the diagram was not:
 * the arc closing it read "score went down" while the node beside it read `569 → 569 correct`.
 * A tab whose entire argument is that its figures are checkable cannot caption a picture with
 * a claim the picture contradicts.
 */
describe('the loop diagram states the direction the numbers show', () => {
  it('says the score did not move when nothing has gone round the loop', async () => {
    mockApi({ labels: { ...LABELS, labels_applied: 0, labels_differing: 0, correct_after: 569 } })
    render(<Trust />)
    await screen.findByTestId('trust-loop-direction')
    const note = document.querySelector('.loop__note')!
    expect(note.textContent).toMatch(/did not move/i)
  })

  it('says it went down when it went down', async () => {
    mockApi()
    render(<Trust />)
    await screen.findByTestId('trust-loop-direction')
    const note = document.querySelector('.loop__note')!
    expect(note.textContent).toMatch(/went down/i)
  })

  it('shows the four buckets rather than an empty bar when nothing was reviewed', async () => {
    mockApi({ labels: { ...LABELS, labels_applied: 0, labels_differing: 0, correct_after: 569 } })
    render(<Trust />)
    const frame = await screen.findByTestId('trust-disagreement')
    // a stacked bar over a total of zero draws nothing, and a heading over nothing reads as a
    // failed render rather than as a count of zero
    expect(within(frame).queryByTestId('trust-disagreement-bar')).not.toBeInTheDocument()
    const buckets = within(frame).getByTestId('trust-disagreement-empty')
    expect(buckets).toHaveTextContent('reviewer corrected a wrong model answer')
    expect(buckets).toHaveTextContent('reviewer differed and overwrote a correct answer')
  })
})

/**
 * What Trust looks like before its artefacts exist.
 *
 * Found by intercepting `/api/admin/**` and looking at the page: every section returns null
 * when its data is null, so the tab rendered a lead paragraph promising "every figure below"
 * and then nothing below it — no loading state, no empty state, no error. On the one tab whose
 * job is to show the evidence, a missing artefact has to be said out loud.
 *
 * The API already answers with the file and the command that writes it. The tab was throwing
 * that away with `r.ok ? r.json() : null`.
 */
describe('missing artefacts are stated, not hidden', () => {
  function mockMissing() {
    const fetchMock = vi.fn(async (url: string) => ({
      ok: false,
      status: 404,
      json: async () => ({
        error: {
          message: `No such artefact yet — run a command and commit it. (${String(url)})`,
        },
      }),
    }))
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch)
  }

  it('names each artefact that has not been produced, and how to produce it', async () => {
    mockMissing()
    render(<Trust />)
    const missing = await screen.findByTestId('trust-missing')
    expect(missing).toHaveTextContent(/calibration/i)
    expect(missing).toHaveTextContent(/measure-selection/i)
    expect(missing).toHaveTextContent(/run a command and commit it/i)
  })

  it('does not promise figures below when there are none', async () => {
    mockMissing()
    render(<Trust />)
    await screen.findByTestId('trust-missing')
    expect(screen.queryByTestId('trust-lead')).not.toBeInTheDocument()
  })

  it('says nothing about missing artefacts when they are all there', async () => {
    mockApi()
    render(<Trust />)
    await screen.findByTestId('trust-accuracy')
    expect(screen.queryByTestId('trust-missing')).not.toBeInTheDocument()
    expect(screen.getByTestId('trust-lead')).toBeInTheDocument()
  })
})

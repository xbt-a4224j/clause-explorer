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

function mockApi() {
  const fetchMock = vi.fn(async (url: string) => {
    const u = String(url)
    // calibration-labels must be matched before calibration — its path is a superstring
    if (u.includes('calibration-labels')) {
      return { ok: true, status: 200, json: async () => LABELS } as Response
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
    // 5 reportable is the Wilson lower bound, not the count of rows at or above 0.70
    const frame = await screen.findByTestId('trust-accuracy')
    expect(frame).toHaveTextContent(/lower bound/i)
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

  it('states that none of the differing decisions was right against gold', async () => {
    mockApi()
    render(<Trust />)
    const frame = await screen.findByTestId('trust-disagreement')
    expect(frame).toHaveTextContent(/none of them was right/i)
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

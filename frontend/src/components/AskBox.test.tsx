import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AskBox } from './AskBox'
import type { AskResponse } from '../types'

/**
 * The free-text box (#47).
 *
 * What earns a test here is not "does it render an input" but the sequence the whole issue is
 * about: a question produces a *selection*, the selection is shown as chips a person can edit,
 * and **nothing executes until they confirm**. A test asserts run-selection is never called
 * before the confirm click — that ordering is the feature, and it is invisible from the markup.
 */

const ASKED: AskResponse = {
  question: 'healthcare cash deals, what did boards get on fiduciary outs',
  measures: ['deal_points.present_count', 'deal_points.n'],
  dimensions: ['deal_points.position'],
  filters: [
    {
      member: 'comparable_deals.label',
      operator: 'equals',
      values: ['Health Care Industry'],
      resolutions: [
        {
          raw: 'healthcare',
          method: 'embedding',
          resolved: 'Health Care Industry',
          similarity: 0.6021,
          matter_count: 26,
          candidates: [],
          note: null,
        },
      ],
    },
    {
      member: 'comparable_deals.consideration_type',
      operator: 'equals',
      values: ['All Cash'],
      resolutions: [
        {
          raw: 'All Cash',
          method: 'verbatim',
          resolved: 'All Cash',
          similarity: null,
          matter_count: null,
          candidates: [],
          note: 'Not an industry label, so the resolution ladder has no vocabulary to check it against.',
        },
      ],
    },
  ],
  time_dimensions: [],
  model_selection: {
    measures: ['deal_points.present_count', 'deal_points.n'],
    dimensions: ['deal_points.position'],
    filters: [],
    timeDimensions: [],
  },
  runnable: true,
  blocked_reason: null,
  usage: {
    model: 'gpt-4o-mini',
    prompt_tokens: 726,
    completion_tokens: 64,
    latency_ms: 2734,
    cost_usd: 0.0001473,
    price_checked_on: '2026-09-03',
    price_source: 'https://developers.openai.com/api/docs/pricing',
  },
}

const UNRESOLVED: AskResponse = {
  ...ASKED,
  filters: [
    {
      member: 'comparable_deals.label',
      operator: 'equals',
      values: [],
      resolutions: [
        {
          raw: 'aerospace',
          method: 'unresolved',
          resolved: null,
          similarity: null,
          matter_count: null,
          candidates: ['Manufacturing Industry', 'Transportation Industry'],
          note: 'The corpus carries no industry by this name.',
        },
      ],
    },
  ],
  runnable: false,
  blocked_reason: "'aerospace' does not match any industry in the corpus.",
}

/** Routes by URL so an assertion about /ask cannot be satisfied by a /run-selection call. */
function mockApi(ask: AskResponse | { error: { message: string } }, askStatus = 200) {
  const calls: string[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(String(url))
    if (String(url).includes('/agent/ask')) {
      return { ok: askStatus < 400, status: askStatus, json: async () => ask } as Response
    }
    if (String(url).includes('run-selection')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          query: JSON.parse(String(init?.body ?? '{}')),
          rows: [{ 'deal_points.present_count': 19, 'deal_points.n': 20 }],
          n: 20,
          refused: false,
          threshold: null,
          message: null,
        }),
      } as Response
    }
    return { ok: true, status: 200, json: async () => ({}) } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

afterEach(() => vi.unstubAllGlobals())

async function ask(question = 'healthcare cash deals') {
  const box = screen.getByTestId('ask-question')
  fireEvent.change(box, { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: /interpret/i }))
  return screen.findByTestId('ask-chips')
}

describe('a question becomes a selection, not an answer', () => {
  it('renders each measure, dimension and filter as its own chip', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    expect(within(chips).getAllByTestId('chip-measure')).toHaveLength(2)
    expect(within(chips).getAllByTestId('chip-dimension')).toHaveLength(1)
    expect(within(chips).getAllByTestId('chip-filter')).toHaveLength(2)
    expect(chips).toHaveTextContent('present_count')
    // the resolved value sits in the chip's edit field, not its text — being editable before
    // the run is the point, so it is asserted as a value rather than as prose
    expect(within(chips).getByLabelText('value for label')).toHaveValue('Health Care Industry')
  })

  it('shows how each filter value was resolved, and its match method', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const filters = within(chips).getAllByTestId('chip-filter')
    // an embedding hit states the tier AND the similarity — "resolved" without a number is
    // an assertion the reader cannot check
    expect(filters[0]).toHaveTextContent(/embedding/i)
    expect(filters[0]).toHaveTextContent('0.60')
    // every number carries its denominator, here the matters behind the resolved value
    expect(filters[0]).toHaveTextContent('n=26')
    // a member the ladder does not cover says so rather than implying a resolution
    expect(filters[1]).toHaveTextContent(/verbatim/i)
  })

  it('renders no figure — the model selected, nothing was computed', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()
    expect(within(chips).queryByTestId('ask-rows')).not.toBeInTheDocument()
  })
})

describe('nothing executes until the user confirms', () => {
  it('does not call run-selection when the interpretation arrives', async () => {
    const calls = mockApi(ASKED)
    render(<AskBox />)
    await ask()
    expect(calls.some((c) => c.includes('run-selection'))).toBe(false)
  })

  it('runs only on the confirm click, and through the existing run-selection path', async () => {
    const calls = mockApi(ASKED)
    render(<AskBox />)
    await ask()

    fireEvent.click(screen.getByRole('button', { name: /run the confirmed selection/i }))
    await waitFor(() => expect(screen.getByTestId('ask-rows')).toBeInTheDocument())
    expect(calls.filter((c) => c.includes('/api/agent/run-selection'))).toHaveLength(1)
  })
})

describe('the chips are editable before anything runs', () => {
  it('removes a measure chip, and the removal reaches the query that is sent', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes('/agent/ask')) {
        return { ok: true, status: 200, json: async () => ASKED } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          query: JSON.parse(String(init?.body ?? '{}')),
          rows: [],
          n: 20,
          refused: false,
          threshold: null,
          message: null,
        }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<AskBox />)
    const chips = await ask()

    const measures = within(chips).getAllByTestId('chip-measure')
    fireEvent.click(within(measures[0]).getByRole('button', { name: /remove/i }))
    await waitFor(() =>
      expect(within(screen.getByTestId('ask-chips')).getAllByTestId('chip-measure')).toHaveLength(
        1,
      ),
    )

    fireEvent.click(screen.getByRole('button', { name: /run the confirmed selection/i }))
    await waitFor(() => expect(screen.getByTestId('ask-sent')).toBeInTheDocument())
    const sent = JSON.parse(
      String((fetchMock.mock.calls.find((c) => String(c[0]).includes('run-selection'))![1] as RequestInit).body),
    )
    expect(sent.measures).toEqual(['deal_points.n'])
  })

  it('lets a filter value be edited, and marks the chip as changed by a person', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const filter = within(chips).getAllByTestId('chip-filter')[0]
    fireEvent.change(within(filter).getByRole('textbox'), {
      target: { value: 'Manufacturing Industry' },
    })
    await waitFor(() =>
      expect(within(screen.getByTestId('ask-chips')).getAllByTestId('chip-filter')[0]).toHaveTextContent(
        /edited/i,
      ),
    )
  })
})

describe('an unresolved value fails loudly rather than returning zero rows', () => {
  it('blocks the run and names what could not be resolved', async () => {
    mockApi(UNRESOLVED)
    render(<AskBox />)
    await ask('aerospace deals')

    expect(screen.getByTestId('ask-blocked')).toHaveTextContent(/aerospace/)
    expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeDisabled()
  })

  it('offers the near misses the corpus does carry', async () => {
    mockApi(UNRESOLVED)
    render(<AskBox />)
    const chips = await ask('aerospace deals')

    const filter = within(chips).getAllByTestId('chip-filter')[0]
    expect(within(filter).getByRole('button', { name: 'Manufacturing Industry' })).toBeInTheDocument()
  })

  it('picking a near miss unblocks the run', async () => {
    mockApi(UNRESOLVED)
    render(<AskBox />)
    const chips = await ask('aerospace deals')

    const filter = within(chips).getAllByTestId('chip-filter')[0]
    fireEvent.click(within(filter).getByRole('button', { name: 'Manufacturing Industry' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeEnabled(),
    )
  })
})

describe('designed states', () => {
  it('reports a failed interpretation rather than an empty selection', async () => {
    mockApi({ error: { message: 'OPENAI_API_KEY is not set.' } }, 503)
    render(<AskBox />)
    const box = screen.getByTestId('ask-question')
    fireEvent.change(box, { target: { value: 'anything' } })
    fireEvent.click(screen.getByRole('button', { name: /interpret/i }))

    expect(await screen.findByTestId('ask-error')).toHaveTextContent(/OPENAI_API_KEY/)
    expect(screen.queryByTestId('ask-chips')).not.toBeInTheDocument()
  })

  it('says so when the model selected nothing, instead of showing an empty chip row', async () => {
    mockApi({
      ...ASKED,
      measures: [],
      dimensions: [],
      filters: [],
      model_selection: { measures: [], dimensions: [], filters: [], timeDimensions: [] },
    })
    render(<AskBox />)
    await ask('something unanswerable')
    expect(screen.getByTestId('ask-empty')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeDisabled()
  })

  it('will not run without a measure — there is nothing to compute', async () => {
    mockApi({ ...ASKED, measures: [] })
    render(<AskBox />)
    await ask()
    expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeDisabled()
  })
})

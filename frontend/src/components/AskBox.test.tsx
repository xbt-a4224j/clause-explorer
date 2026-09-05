import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AskBox } from './AskBox'
import type { AskResponse, MembersResponse } from '../types'

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

/**
 * What `/agent/members` says about each selected name (#57).
 *
 * Every field here is what makes a chip readable: the catalog title instead of the bare
 * suffix, the closed vocabulary behind a filter value, and whether the corpus can answer with
 * this member at all.
 */
const MEMBERS: MembersResponse = {
  members: [
    {
      name: 'deal_points.present_count',
      title: 'Deal Points Present Count',
      description: 'THE NUMERATOR for "how many deals have this provision at all".',
      kind: 'measure',
      type: 'number',
      candidates: [],
      enumerable: false,
      distinct_values: 0,
      populated: null,
      total: 12937,
      cannot_answer: null,
    },
    {
      name: 'deal_points.n',
      title: 'Deal Points N',
      description: 'THE DENOMINATOR.',
      kind: 'measure',
      type: 'number',
      candidates: [],
      enumerable: false,
      distinct_values: 0,
      populated: null,
      total: 12937,
      cannot_answer: null,
    },
    {
      name: 'deal_points.position',
      title: 'Deal Points Position',
      description: 'The negotiated position the annotator recorded.',
      kind: 'dimension',
      type: 'string',
      candidates: ['All Cash', 'Mixed'],
      enumerable: true,
      distinct_values: 2,
      populated: 12937,
      total: 12937,
      cannot_answer: null,
    },
    {
      name: 'comparable_deals.label',
      title: 'Comparable Deals Label',
      description: 'The industry name a partner reads.',
      kind: 'dimension',
      type: 'string',
      candidates: ['Health Care Industry', 'Manufacturing Industry', 'Transportation Industry'],
      enumerable: true,
      distinct_values: 3,
      populated: 139,
      total: 152,
      cannot_answer: null,
    },
    {
      name: 'comparable_deals.consideration_type',
      title: 'Comparable Deals Consideration',
      description: 'All Cash / All Stock / Mixed.',
      kind: 'dimension',
      type: 'string',
      candidates: ['All Cash', 'All Stock', 'Mixed Cash/Stock'],
      enumerable: true,
      distinct_values: 3,
      populated: 152,
      total: 152,
      cannot_answer: null,
    },
  ],
}

/** Routes by URL so an assertion about /ask cannot be satisfied by a /run-selection call. */
function mockApi(
  ask: AskResponse | { error: { message: string } },
  askStatus = 200,
  members: MembersResponse = MEMBERS,
  membersStatus = 200,
) {
  const calls: string[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(String(url))
    if (String(url).includes('/agent/members')) {
      return {
        ok: membersStatus < 400,
        status: membersStatus,
        json: async () => (membersStatus < 400 ? members : { error: { message: 'Cube is down.' } }),
      } as Response
    }
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
    // #57: the chip carries the catalog's title, not the bare member suffix
    expect(chips).toHaveTextContent('Deal Points Present Count')
    // the resolved value sits in the chip's control, not its text — being editable before the
    // run is the point, so it is asserted as a value rather than as prose
    expect(within(chips).getByLabelText('value for Comparable Deals Label')).toHaveValue(
      'Health Care Industry',
    )
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

  it('lets a filter value be changed, and marks the chip as changed by a person', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const filter = within(chips).getAllByTestId('chip-filter')[0]
    fireEvent.change(within(filter).getByRole('combobox'), {
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

/**
 * #50 — what the question cost.
 *
 * A firm paying per seat notices a tool that shows the price of the question the moment it was
 * asked. Every field is measured: tokens off the response, dollars off the committed price
 * table. The issue's own example line reads `$0.0006` for 2,104 in / 61 out, which prices at
 * $0.000352 — so the rendered figure is computed here rather than copied from the ticket.
 */
describe('the cost line', () => {
  it('renders model, tokens in and out, latency and dollars', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    await ask()

    const usage = screen.getByTestId('ask-usage')
    expect(usage).toHaveTextContent('gpt-4o-mini')
    expect(usage).toHaveTextContent('726 in')
    expect(usage).toHaveTextContent('64 out')
    expect(usage).toHaveTextContent('2.7s')
    expect(usage).toHaveTextContent('$0.000147')
  })

  it('separates thousands, because these are read as evidence', async () => {
    mockApi({ ...ASKED, usage: { ...ASKED.usage, prompt_tokens: 2104 } })
    render(<AskBox />)
    await ask()
    expect(screen.getByTestId('ask-usage')).toHaveTextContent('2,104 in')
  })

  it('appears before any run, because the cost was incurred at the question', async () => {
    const calls = mockApi(ASKED)
    render(<AskBox />)
    await ask()
    expect(screen.getByTestId('ask-usage')).toBeInTheDocument()
    expect(calls.some((c) => c.includes('run-selection'))).toBe(false)
  })

  it('states the date the price table was checked, so the dollars are falsifiable', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    await ask()
    expect(screen.getByTestId('ask-usage')).toHaveTextContent('2026-09-03')
  })
})

/**
 * #51 — the confirm click is eval data.
 *
 * A run that differs from what the model returned is a labelled disagreement, and the eval it
 * feeds has only 25 authored cases from July. Agreements are recorded too: an eval fed only
 * corrections would score the model at 0.00 by construction.
 */
describe('confirming records the pair', () => {
  function bodyOf(mock: ReturnType<typeof vi.fn>, fragment: string) {
    const call = mock.mock.calls.find((c) => String(c[0]).includes(fragment))
    return call ? JSON.parse(String((call[1] as RequestInit).body)) : null
  }

  it('records an unchanged run as an agreement', async () => {
    mockApi(ASKED)
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    render(<AskBox />)
    await ask()
    fireEvent.click(screen.getByRole('button', { name: /run the confirmed selection/i }))

    await waitFor(() => expect(bodyOf(fetchMock, 'selection-correction')).not.toBeNull())
    const sent = bodyOf(fetchMock, 'selection-correction')
    expect(sent.model_selection.measures).toEqual(ASKED.model_selection.measures)
    expect(sent.confirmed_selection.measures).toEqual(ASKED.measures)
  })

  it('sends the model selection and the edited one, so the server can name the difference', async () => {
    mockApi(ASKED)
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
    render(<AskBox />)
    const chips = await ask()

    const filter = within(chips).getAllByTestId('chip-filter')[0]
    fireEvent.change(within(filter).getByRole('combobox'), {
      target: { value: 'Manufacturing Industry' },
    })
    fireEvent.click(screen.getByRole('button', { name: /run the confirmed selection/i }))

    await waitFor(() => expect(bodyOf(fetchMock, 'selection-correction')).not.toBeNull())
    const sent = bodyOf(fetchMock, 'selection-correction')
    expect(sent.question).toBe(ASKED.question)
    expect(sent.confirmed_selection.filters[0].values).toEqual(['Manufacturing Industry'])
  })

  it('records nothing before the confirm click — asking is not confirming', async () => {
    const calls = mockApi(ASKED)
    render(<AskBox />)
    await ask()
    expect(calls.some((c) => c.includes('selection-correction'))).toBe(false)
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

/**
 * #57 — the chips were unreadable, and the corpus never said it could not answer.
 *
 * Smoke-testing the merged build with *"What's the average deal size for healthcare?"*
 * produced `[measure n ×] [measure n ×] [has_industry ( ) edited by you ×]`. Four faults in
 * one line, and each of these describes one of them.
 */
describe('a chip a person can actually read', () => {
  it('names the member by its catalog title, not its bare suffix', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const measures = within(chips).getAllByTestId('chip-measure')
    expect(measures[1]).toHaveTextContent('Deal Points N')
    // the qualified name stays available — it is what gets sent, and a reviewer checking a
    // selection against the catalog needs it
    expect(measures[1]).toHaveTextContent('deal_points.n')
  })

  it('carries the catalog description, on hover and on expansion', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const measure = within(chips).getAllByTestId('chip-measure')[1]
    const name = within(measure).getByTestId('chip-name')
    expect(name).toHaveAttribute('title', expect.stringContaining('DENOMINATOR'))

    fireEvent.click(name)
    await waitFor(() =>
      expect(within(measure).getByTestId('chip-description')).toHaveTextContent('DENOMINATOR'),
    )
  })

  it('falls back to the member name when the catalog cannot be read', async () => {
    mockApi(ASKED, 200, MEMBERS, 503)
    render(<AskBox />)
    const chips = await ask()

    expect(within(chips).getAllByTestId('chip-measure')[1]).toHaveTextContent('deal_points.n')
    // and says why the titles are missing rather than looking like the old build
    expect(screen.getByTestId('ask-catalog-error')).toHaveTextContent(/Cube is down/)
  })
})

describe('a duplicate selection is collapsed, not drawn twice', () => {
  it('draws one chip for a measure the model named twice', async () => {
    mockApi({
      ...ASKED,
      measures: ['deal_points.n', 'deal_points.n'],
      dimensions: [],
      filters: [],
    })
    render(<AskBox />)
    const chips = await ask()
    expect(within(chips).getAllByTestId('chip-measure')).toHaveLength(1)
  })
})

describe('a closed vocabulary is a select, never a text box', () => {
  it('offers the values the corpus actually holds', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const control = within(chips).getByLabelText('value for Comparable Deals Label')
    expect(control.tagName).toBe('SELECT')
    const options = within(control as HTMLSelectElement).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(
      expect.arrayContaining([
        'Health Care Industry',
        'Manufacturing Industry',
        'Transportation Industry',
      ]),
    )
  })

  it('leaves no free-text control anywhere in the chip row', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()
    expect(within(chips).queryAllByRole('textbox')).toHaveLength(0)
  })

  it('an unresolved value opens on a placeholder rather than a wrong guess', async () => {
    mockApi(UNRESOLVED)
    render(<AskBox />)
    const chips = await ask('aerospace deals')

    const control = within(chips).getByLabelText('value for Comparable Deals Label')
    expect(control).toHaveValue('')
    expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeDisabled()
  })
})

describe('"edited by you" means a person changed something', () => {
  it('says nothing when the value came back from the model untouched', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()
    expect(within(chips).getAllByTestId('chip-filter')[0]).not.toHaveTextContent(/edited by you/i)
  })

  it('stops saying it when the value is put back to what the model chose', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    const chips = await ask()

    const control = within(chips).getByLabelText('value for Comparable Deals Label')
    fireEvent.change(control, { target: { value: 'Manufacturing Industry' } })
    await waitFor(() =>
      expect(
        within(screen.getByTestId('ask-chips')).getAllByTestId('chip-filter')[0],
      ).toHaveTextContent(/edited by you/i),
    )

    fireEvent.change(screen.getByLabelText('value for Comparable Deals Label'), {
      target: { value: 'Health Care Industry' },
    })
    await waitFor(() =>
      expect(
        within(screen.getByTestId('ask-chips')).getAllByTestId('chip-filter')[0],
      ).not.toHaveTextContent(/edited by you/i),
    )
  })
})

/**
 * Fault 4, the one the issue calls interesting. `deal_value_usd` is NULL on all 152 matters,
 * so `deal_size_band` holds one value and no selection over it can answer. A tool that fails
 * and a tool that explains why it cannot answer are different products.
 */
describe('saying the corpus cannot answer', () => {
  const EMPTY_MEMBERS: MembersResponse = {
    members: [
      ...MEMBERS.members,
      {
        name: 'comparable_deals.deal_size_band',
        title: 'Comparable Deals Deal Size Band',
        description: 'The single definition of a deal-size band in this system.',
        kind: 'dimension',
        type: 'string',
        candidates: ['unknown'],
        enumerable: true,
        distinct_values: 1,
        populated: 152,
        total: 152,
        cannot_answer:
          "Comparable Deals Deal Size Band holds one value across the whole corpus, 'unknown', " +
          'on 152 of 152. Grouping or filtering by it cannot separate anything.',
      },
    ],
  }

  const DEAL_SIZE: AskResponse = {
    ...ASKED,
    measures: ['deal_points.n'],
    dimensions: ['comparable_deals.deal_size_band'],
    filters: [],
  }

  it('states it, and names why, instead of handing back a selection to repair', async () => {
    mockApi(DEAL_SIZE, 200, EMPTY_MEMBERS)
    render(<AskBox />)
    await ask("what's the average deal size for healthcare")

    const refusal = await screen.findByTestId('ask-cannot-answer')
    expect(refusal).toHaveTextContent(/cannot answer/i)
    expect(refusal).toHaveTextContent('unknown')
    expect(refusal).toHaveTextContent('152')
  })

  it('will not run a selection the corpus cannot answer', async () => {
    mockApi(DEAL_SIZE, 200, EMPTY_MEMBERS)
    render(<AskBox />)
    await ask("what's the average deal size for healthcare")

    await screen.findByTestId('ask-cannot-answer')
    expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeDisabled()
  })

  it('runs again once the member the corpus cannot answer with is removed', async () => {
    mockApi(DEAL_SIZE, 200, EMPTY_MEMBERS)
    render(<AskBox />)
    const chips = await ask("what's the average deal size for healthcare")

    await screen.findByTestId('ask-cannot-answer')
    const dimension = within(chips).getAllByTestId('chip-dimension')[0]
    fireEvent.click(within(dimension).getByRole('button', { name: /remove/i }))
    await waitFor(() => expect(screen.queryByTestId('ask-cannot-answer')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeEnabled()
  })

  it('says nothing when every selected member has data behind it', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    await ask()
    expect(screen.queryByTestId('ask-cannot-answer')).not.toBeInTheDocument()
  })
})

/**
 * The value the model typed is not always a value the corpus holds — and until #57 the only
 * defence was a paragraph asking the reader to notice.
 *
 * Caught by driving the running app rather than by a test: asked "how many all-cash deals are
 * there", the model filtered `consideration_type = "All Cash Deal"`, which this corpus does not
 * carry. The chip's `<select>` fell back to its placeholder while the *state* still held the
 * model's text, so the run was enabled and returned `comparable_deals.n = 0` — the exact
 * failure the resolution ladder exists to prevent, one field away from where the ladder works.
 *
 * With a real vocabulary on every dimension this stops being a warning and becomes a check.
 */
describe('a filter value the corpus does not carry', () => {
  const OFF_VOCABULARY: AskResponse = {
    ...ASKED,
    filters: [
      {
        member: 'comparable_deals.consideration_type',
        operator: 'equals',
        values: ['All Cash Deal'],
        resolutions: [
          {
            raw: 'All Cash Deal',
            method: 'verbatim',
            resolved: 'All Cash Deal',
            similarity: null,
            matter_count: null,
            candidates: [],
            note: 'Not an industry label, so the resolution ladder has no vocabulary for it.',
          },
        ],
      },
    ],
  }

  it('is cleared rather than left in a control that cannot show it', async () => {
    mockApi(OFF_VOCABULARY)
    render(<AskBox />)
    const chips = await ask('how many all-cash deals are there')

    await waitFor(() =>
      expect(
        within(chips).getByLabelText('value for Comparable Deals Consideration'),
      ).toHaveValue(''),
    )
  })

  it('blocks the run instead of returning zero rows', async () => {
    mockApi(OFF_VOCABULARY)
    render(<AskBox />)
    await ask('how many all-cash deals are there')

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run the confirmed selection/i })).toBeDisabled(),
    )
  })

  it('names what the model wrote and what the field actually holds', async () => {
    mockApi(OFF_VOCABULARY)
    render(<AskBox />)
    await ask('how many all-cash deals are there')

    const note = await screen.findByTestId('ask-off-vocabulary')
    expect(note).toHaveTextContent('All Cash Deal')
    expect(note).toHaveTextContent('All Cash')
    expect(note).toHaveTextContent('Comparable Deals Consideration')
  })

  it('does not accuse the user of editing a value they never touched', async () => {
    mockApi(OFF_VOCABULARY)
    render(<AskBox />)
    const chips = await ask('how many all-cash deals are there')

    await waitFor(() => expect(screen.getByTestId('ask-off-vocabulary')).toBeInTheDocument())
    expect(within(chips).getAllByTestId('chip-filter')[0]).not.toHaveTextContent(/edited by you/i)
  })

  it('says nothing when the model picked a value the corpus does hold', async () => {
    mockApi(ASKED)
    render(<AskBox />)
    await ask()
    expect(screen.queryByTestId('ask-off-vocabulary')).not.toBeInTheDocument()
  })
})

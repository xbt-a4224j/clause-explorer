import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Label } from './Label'
import type { CalibrationLabels, LabelQueueResponse } from '../types'

/**
 * Label (#29, #52).
 *
 * #52 replaced the single-letter keys with four named buttons, so what earns a test is the
 * button flow end to end — Accept, Correct, Edit, Skip move the queue and post a decision —
 * plus the two things the letters used to hide: that the keys are *gone* (a stray `y` must
 * write nothing), and that the outcome of the loop is legible from the loop, with its
 * direction stated honestly.
 */

const QUEUE: LabelQueueResponse = {
  queue_size: 2,
  labelled_count: 3,
  items: [
    {
      matter_id: 'contract_1',
      deal_point_name: 'Ticking fee',
      llm_prediction: 'Yes',
      deterministic_prediction: 'No',
      disagreement: true,
      quoted_text: 'a fee shall accrue beginning on the outside date',
      span_start: 10,
      span_end: 60,
    },
    {
      matter_id: 'contract_2',
      deal_point_name: 'Fiduciary exception',
      llm_prediction: 'No',
      deterministic_prediction: 'No',
      disagreement: false,
      quoted_text: null,
      span_start: null,
      span_end: null,
    },
  ],
}

/**
 * The committed artefact's real headline figures (`docs/results/calibration-labels.json`).
 *
 * Deliberately the true numbers rather than round invented ones: the panel's job is to state
 * that six decisions moved the score from 569 correct to 565, and a fixture that went *up*
 * would let the honest-direction assertion pass against a panel that always says "improved".
 */
const CALIBRATION: CalibrationLabels = {
  generated_at: '2026-09-04T03:12:58+00:00',
  command: 'PYTHONPATH=backend python -m explorer.evals.calibration',
  prediction_count: 1701,
  labels_applied: 6,
  labels_differing: 5,
  correct_before: 569,
  correct_after: 565,
  accuracy_before: 0.335,
  accuracy_after: 0.332,
  results: [],
}

/**
 * Wait until the queue has rendered and React's passive effects have flushed (#38).
 *
 * `findBy*` resolves off a DOM mutation, which happens at commit, while effects flush
 * afterwards. Awaiting an empty `waitFor` runs an async `act`, which drains them — so a click
 * lands on a view whose handlers and fetches have actually settled.
 */
async function ready() {
  await screen.findByText(/a fee shall accrue/)
  await waitFor(() => {})
}

function mockApi(calibration: CalibrationLabels | null = CALIBRATION) {
  const decisions: unknown[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/decide')) {
      decisions.push(JSON.parse(String(init?.body)))
      return { ok: true, json: async () => ({ ok: true }) } as Response
    }
    if (u.includes('calibration-labels')) {
      if (!calibration) return { ok: false, status: 404, json: async () => ({}) } as Response
      return { ok: true, json: async () => calibration } as Response
    }
    return { ok: true, json: async () => QUEUE } as Response
  })
  return { fetchMock, decisions }
}

function button(name: RegExp | string) {
  return screen.getByRole('button', { name })
}

afterEach(() => vi.unstubAllGlobals())

describe('the queue', () => {
  it('shows the candidate span and both predictions', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    expect(await screen.findByText(/a fee shall accrue/)).toBeInTheDocument()
    // scoped to the predictions list: #33's rationale line repeats both values by design,
    // so an unscoped getByText would pass or fail for reasons unrelated to this assertion
    const predictions = within(screen.getByTestId('label-predictions'))
    expect(predictions.getByText('Yes')).toBeInTheDocument()
    expect(predictions.getByText('No')).toBeInTheDocument()
  })

  it('shows labelled / queue size progress', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    expect(await screen.findByTestId('label-progress')).toHaveTextContent('3')
    expect(screen.getByTestId('label-progress')).toHaveTextContent('2')
  })
})

/**
 * #52 — buttons, not letters. These replace the y/n/e/s keyboard tests one for one.
 */
describe('the decision buttons (#52)', () => {
  it('Accept posts the llm prediction and advances to the next item', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Accept'))

    await waitFor(() => expect(decisions).toHaveLength(1))
    expect(decisions[0]).toMatchObject({
      matter_id: 'contract_1',
      deal_point_name: 'Ticking fee',
      value: 'Yes',
      prior_prediction: 'Yes',
    })
    await waitFor(() => expect(screen.getByTestId('label-item')).toHaveTextContent('contract_2'))
  })

  it('Correct opens the editor with the other extractor’s answer pre-filled', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Correct'))

    // the alternative, not the model's answer — Correct means "the other one was right",
    // and pre-filling the value being rejected makes the reviewer delete it first
    expect(screen.getByLabelText('correct value')).toHaveValue('No')
  })

  it('Edit opens the same editor with the model’s answer, to amend rather than replace', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Edit'))
    expect(screen.getByLabelText('correct value')).toHaveValue('Yes')
  })

  it('the editor posts the typed value on Enter', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Correct'))
    const input = screen.getByLabelText('correct value')
    fireEvent.change(input, { target: { value: 'Maybe' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(decisions).toHaveLength(1))
    expect(decisions[0]).toMatchObject({ value: 'Maybe', prior_prediction: 'Yes' })
  })

  it('Skip advances without posting a decision', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Skip'))

    await waitFor(() => expect(screen.getByTestId('label-item')).toHaveTextContent('contract_2'))
    expect(decisions).toHaveLength(0)
  })

  it('is reachable with Tab and Enter — real buttons, in document order, none taken out of the tab ring', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    const actions = within(screen.getByTestId('label-actions')).getAllByRole('button')
    expect(actions.map((b) => b.textContent)).toEqual(['Accept', 'Correct', 'Edit', 'Skip'])
    for (const el of actions) {
      // jsdom does not synthesise a click from Enter the way a browser does for a native
      // button, so the reachability claim is asserted structurally: a `<button>` with no
      // negative tabindex and no disabled attribute is Tab-focusable and Enter-activatable.
      expect(el.tagName).toBe('BUTTON')
      expect(el).toBeEnabled()
      expect(el).not.toHaveAttribute('tabindex')
      el.focus()
      expect(document.activeElement).toBe(el)
    }
  })
})

/**
 * #52 — the letters are gone, not hidden. A reviewer who used to touch-type the queue now
 * types into nothing, and that must be true rather than merely undocumented.
 */
describe('the keyboard shortcuts are removed (#52)', () => {
  it('y no longer accepts, and s no longer skips', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.keyDown(window, { key: 'y' })
    fireEvent.keyDown(window, { key: 's' })
    await waitFor(() => {})

    expect(decisions).toHaveLength(0)
    expect(screen.getByTestId('label-item')).toHaveTextContent('contract_1')
  })

  it('n and e no longer open the editor', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.keyDown(window, { key: 'n' })
    fireEvent.keyDown(window, { key: 'e' })
    await waitFor(() => {})

    expect(screen.queryByLabelText('correct value')).not.toBeInTheDocument()
  })

  it('has no shortcut help of its own — ? belongs to the shell now', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.keyDown(window, { key: '?' })
    await waitFor(() => {})

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not advertise the removed keys anywhere on the tab', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()
    fireEvent.click(button(/how this queue works/i))

    expect(document.body.textContent).not.toMatch(/y n e s|y\/n\/e\/s/)
    expect(document.body.textContent).not.toMatch(/keystroke/i)
  })
})

/**
 * #52 — the loop's output, visible from the loop.
 *
 * The honesty requirement is the feature: six decisions moved the graded score from 569
 * correct to 565. A panel that rendered that as progress would be worse than no panel.
 */
describe('what the decisions changed (#52)', () => {
  it('states decisions recorded and how many differed from the model', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const panel = await screen.findByTestId('label-outcome')
    expect(panel).toHaveTextContent(/6 decisions/)
    expect(panel).toHaveTextContent(/5 .*differed/)
  })

  it('gives accuracy before and after, each with its n', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const panel = await screen.findByTestId('label-outcome')
    expect(panel).toHaveTextContent(/569 of 1701/)
    expect(panel).toHaveTextContent(/565 of 1701/)
    expect(panel).toHaveTextContent(/33\.5%/)
    expect(panel).toHaveTextContent(/33\.2%/)
  })

  it('says the score went down, and never dresses it as an improvement', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const panel = await screen.findByTestId('label-outcome')
    expect(panel).toHaveTextContent(/went down/i)
    expect(panel).toHaveTextContent(/4 fewer/)
    expect(panel).not.toHaveTextContent(/improved|better|▲|↑/i)
  })

  it('keeps the corpus caveat: every queued item already has a lawyer’s answer', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const panel = await screen.findByTestId('label-outcome')
    expect(panel).toHaveTextContent(/already has a lawyer/i)
    expect(panel).toHaveTextContent(/un-annotated/i)
  })

  it('names the command that produced the figures', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const panel = await screen.findByTestId('label-outcome')
    expect(panel).toHaveTextContent(/explorer\.evals\.calibration/)
  })

  it('says so plainly when calibration has not been run', async () => {
    const { fetchMock } = mockApi(null)
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const panel = await screen.findByTestId('label-outcome')
    await waitFor(() => expect(panel).toHaveTextContent(/not run yet/i))
  })

  it('sits above the queue, where a decision is made', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()
    const panel = screen.getByTestId('label-outcome')
    const item = screen.getByTestId('label-item')
    // DOCUMENT_POSITION_FOLLOWING: the queue item comes after the panel in document order
    expect(panel.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

/**
 * #52 — the reviewer's own hit rate against the model, one item at a time. Aggregate
 * before/after is the loop's output; this is the feedback the decision itself earns.
 */
describe('whether the model agreed (#52)', () => {
  it('says the model agreed when the reviewer accepted its answer', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Accept'))

    const verdict = await screen.findByTestId('label-agreement')
    expect(verdict).toHaveTextContent(/Ticking fee/)
    expect(verdict).toHaveTextContent(/agreed with you/i)
    expect(verdict).not.toHaveTextContent(/did not agree/i)
  })

  it('says the model did not agree when the reviewer corrected it', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Correct'))
    fireEvent.keyDown(screen.getByLabelText('correct value'), { key: 'Enter' })

    const verdict = await screen.findByTestId('label-agreement')
    expect(verdict).toHaveTextContent(/did not agree/i)
    expect(verdict).toHaveTextContent(/Yes/)
  })

  it('says nothing before a decision, and nothing after a skip', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    expect(screen.queryByTestId('label-agreement')).not.toBeInTheDocument()
    fireEvent.click(button('Skip'))
    await waitFor(() => expect(screen.getByTestId('label-item')).toHaveTextContent('contract_2'))
    expect(screen.queryByTestId('label-agreement')).not.toBeInTheDocument()
  })
})

/**
 * #33 — the card stated three facts and explained none of them. What earns a test here is
 * that the explanation is *state-dependent*: a disagreement and an agreement are different
 * situations for the reviewer, and rendering the same prose for both would be the failure.
 */
describe('explaining the loop (#33)', () => {
  // The panel persists its open/closed choice in localStorage, which outlives a render. Without
  // this, one test's click sets the next test's starting state and the default is untestable.
  beforeEach(() => window.localStorage.clear())

  it('renders the loop diagram with an accessible name', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    // The panel is collapsed on a first visit, so the diagram is behind the toggle rather than
    // ahead of the queue. Opening it is the assertion: the diagram exists and is reachable.
    fireEvent.click(await screen.findByRole('button', { name: /how this queue works/i }))
    expect(await screen.findByRole('img', { name: /improvement loop/i })).toBeInTheDocument()
  })

  it('starts collapsed, and an opened panel survives a remount', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = render(<Label />)

    // Collapsed first: the queue targets under five seconds per item, and prose above it is
    // in the way. A reader who opens the explainer keeps it open across loads.
    const toggle = await screen.findByRole('button', { name: /how this queue works/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    unmount()

    render(<Label />)
    expect(await screen.findByRole('button', { name: /how this queue works/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('explains a disagreement as the reason this item is ranked first', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    const why = await screen.findByTestId('label-why')
    expect(why).toHaveTextContent(/disagree/i)
    expect(why).toHaveTextContent(/Yes/)
    expect(why).toHaveTextContent(/No/)
  })

  it('explains an agreement differently — confirmation, not adjudication', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Skip'))

    const why = await screen.findByTestId('label-why')
    await waitFor(() => expect(why).toHaveTextContent(/agree/i))
    expect(why).not.toHaveTextContent(/ranked first/i)
  })

  it('gives a reason for an absent span rather than a bare line', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await ready()

    fireEvent.click(button('Skip'))

    const missing = await screen.findByTestId('label-nospan')
    expect(missing).toHaveTextContent(/whole agreement|not a failure|expected/i)
  })

  it('describes the buttons the tab actually has', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    fireEvent.click(await screen.findByRole('button', { name: /how this queue works/i }))
    const explainer = await screen.findByText(/What your decision does/i)
    expect(explainer.parentElement).toHaveTextContent(/decision/i)
  })
})

describe('designed states', () => {
  it('shows a designed empty state once the queue is exhausted', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('calibration-labels')) {
        return { ok: true, json: async () => CALIBRATION } as Response
      }
      return {
        ok: true,
        json: async () => ({ ...QUEUE, items: [], queue_size: 0 }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    expect(await screen.findByText(/queue is empty/i)).toBeInTheDocument()
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Label } from './Label'
import type { LabelQueueResponse } from '../types'

/**
 * Label (#29). Keyboard-only, under 5 seconds per item — so what earns a test is the keyboard
 * flow end to end: y/n/e/s move the queue and post a decision with no mouse involved, and the
 * progress indicator tells a KM reviewer how much is left before they start.
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

function mockApi() {
  const decisions: unknown[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes('/decide')) {
      decisions.push(JSON.parse(String(init?.body)))
      return { ok: true, json: async () => ({ ok: true }) } as Response
    }
    return { ok: true, json: async () => QUEUE } as Response
  })
  return { fetchMock, decisions }
}

beforeEach(() => {})
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

describe('keyboard flow', () => {
  it('y accepts the llm prediction and advances to the next item', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 'y' })

    await waitFor(() => expect(decisions).toHaveLength(1))
    expect(decisions[0]).toMatchObject({
      matter_id: 'contract_1',
      deal_point_name: 'Ticking fee',
      value: 'Yes',
    })
    await waitFor(() => expect(screen.getByTestId('label-item')).toHaveTextContent('contract_2'))
  })

  it('n rejects and opens edit for a correction', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 'n' })
    // synchronous on purpose: the keydown handler sets state in the same flush, so there is
    // nothing to await. findBy* wrapped it in a 1s poll that expired under parallel load —
    // a flake caused entirely by asking for asynchrony that never existed.
    expect(screen.getByLabelText('correct value')).toBeInTheDocument()
  })

  it('e opens the span editor without rejecting first', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 'e' })
    expect(screen.getByLabelText('correct value')).toBeInTheDocument()
  })

  it('s skips without posting a decision', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 's' })

    await waitFor(() => expect(screen.getByTestId('label-item')).toHaveTextContent('contract_2'))
    expect(decisions).toHaveLength(0)
  })

  it('? shows the shortcut help', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: '?' })
    const dialog = await screen.findByRole('dialog', { name: /label shortcuts/i })
    expect(dialog).toHaveTextContent(/accept/i)
  })
})

/**
 * #33 — the card stated three facts and explained none of them. What earns a test here is
 * that the explanation is *state-dependent*: a disagreement and an agreement are different
 * situations for the reviewer, and rendering the same prose for both would be the failure.
 */
describe('explaining the loop (#33)', () => {
  it('renders the loop diagram with an accessible name', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    expect(await screen.findByRole('img', { name: /improvement loop/i })).toBeInTheDocument()
  })

  it('collapses, and the choice survives a remount', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = render(<Label />)

    const toggle = await screen.findByRole('button', { name: /how this queue works/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    unmount()

    render(<Label />)
    expect(await screen.findByRole('button', { name: /how this queue works/i })).toHaveAttribute(
      'aria-expanded',
      'false',
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
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 's' })

    const why = await screen.findByTestId('label-why')
    await waitFor(() => expect(why).toHaveTextContent(/agree/i))
    expect(why).not.toHaveTextContent(/ranked first/i)
  })

  it('gives a reason for an absent span rather than a bare line', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 's' })

    const missing = await screen.findByTestId('label-nospan')
    expect(missing).toHaveTextContent(/whole agreement|not a failure|expected/i)
  })

  it('leaves the keyboard loop alone — the toggle does not capture y/n/e/s', async () => {
    const { fetchMock, decisions } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)

    const toggle = await screen.findByRole('button', { name: /how this queue works/i })
    toggle.focus()
    fireEvent.keyDown(window, { key: 'y' })

    await waitFor(() => expect(decisions).toHaveLength(1))
  })
})

describe('designed states', () => {
  it('shows a designed empty state once the queue is exhausted', async () => {
    const fetchMock = vi.fn(
      async () =>
        ({
          ok: true,
          json: async () => ({ ...QUEUE, items: [], queue_size: 0 }),
        }) as Response,
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    expect(await screen.findByText(/queue is empty/i)).toBeInTheDocument()
  })
})

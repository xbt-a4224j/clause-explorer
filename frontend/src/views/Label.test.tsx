import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    expect(screen.getByText('Yes')).toBeInTheDocument()
    expect(screen.getByText('No')).toBeInTheDocument()
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
    expect(await screen.findByLabelText('correct value')).toBeInTheDocument()
  })

  it('e opens the span editor without rejecting first', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Label />)
    await screen.findByText(/a fee shall accrue/)

    fireEvent.keyDown(window, { key: 'e' })
    expect(await screen.findByLabelText('correct value')).toBeInTheDocument()
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

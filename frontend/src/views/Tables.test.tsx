import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Tables } from './Tables'

/** Tables (#31) — server-side sort/filter/pagination; the view never asks for more than a page. */

const SCHEMA = {
  table: 'matters',
  row_count: 152,
  columns: [
    { name: 'id', type: 'text', null_count: 0, is_inferred_flag: false },
    { name: 'is_inferred_industry', type: 'boolean', null_count: 0, is_inferred_flag: true },
  ],
}

const ROWS = {
  table: 'matters',
  total_count: 152,
  rows: [{ id: 'contract_1', is_inferred_industry: true }],
  limit: 25,
  offset: 0,
}

function mockApi() {
  const calls: string[] = []
  const fetchMock = vi.fn(async (url: string) => {
    calls.push(String(url))
    if (String(url).includes('/schema')) return { ok: true, json: async () => SCHEMA } as Response
    if (String(url).includes('/rows/contract_1'))
      return { ok: true, json: async () => ({ id: 'contract_1', full: true }) } as Response
    return { ok: true, json: async () => ROWS } as Response
  })
  return { fetchMock, calls }
}

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})
afterEach(() => vi.unstubAllGlobals())

describe('browsing', () => {
  it('shows column type and null count in the header', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Tables />)
    expect(await screen.findByText(/boolean · null=0/)).toBeInTheDocument()
  })

  it('flags an inferred column consistently with the matter card', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Tables />)
    // the column name "is_inferred_industry" itself contains the substring "inferred", so
    // scope to the dedicated marker rather than an unscoped text match
    expect(await screen.findByText('· inferred', { exact: false })).toBeInTheDocument()
  })

  it('never requests more than one page at a time', async () => {
    const { fetchMock, calls } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Tables />)
    await screen.findByTestId('row-contract_1')
    const rowsCall = calls.find((c) => c.includes('/rows?'))
    expect(rowsCall).toContain('limit=25')
  })
})

describe('row expansion', () => {
  it('shows the full record on click', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Tables />)
    const row = await screen.findByTestId('row-contract_1')
    fireEvent.click(row)
    expect(await screen.findByText('full')).toBeInTheDocument()
  })
})

describe('deep-linkable state', () => {
  it('mirrors table and filter into the URL', async () => {
    const { fetchMock } = mockApi()
    vi.stubGlobal('fetch', fetchMock)
    render(<Tables />)
    await screen.findByTestId('row-contract_1')
    expect(window.location.search).toContain('table=matters')
  })
})

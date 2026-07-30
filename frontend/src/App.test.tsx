import { render, screen, waitFor } from '@testing-library/react'
import { App } from './App'

describe('App shell', () => {
  it('renders the brand mark', () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('offline'))) as unknown as typeof fetch
    render(<App />)
    expect(screen.getByText('clause explorer')).toBeInTheDocument()
  })

  it('shows each dependency separately when the api responds', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: 'ok', db: 'ok', cube: 'ok', version: '0.1.0' }),
      }),
    ) as unknown as typeof fetch
    render(<App />)
    await waitFor(() => expect(screen.getByText('cube')).toBeInTheDocument())
    expect(screen.getByText('db')).toBeInTheDocument()
  })

  it('degrades visibly when the api is unreachable', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('boom'))) as unknown as typeof fetch
    render(<App />)
    await waitFor(() => expect(screen.getByText(/api unreachable/)).toBeInTheDocument())
  })
})

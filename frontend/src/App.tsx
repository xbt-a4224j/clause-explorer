/**
 * Issue #1 scope: prove the fourth service builds and serves, and that the API is
 * reachable through it. The six-tab shell and keyboard navigation land in #5.
 */
import { useEffect, useState } from 'react'

type Health = { status: string; db: string; cube: string; version: string }

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/healthz')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main style={{ padding: 'var(--pad-lg)', fontFamily: 'var(--font-mono)' }}>
      <h1 style={{ color: 'var(--accent)', fontSize: '1rem', fontWeight: 500, margin: 0 }}>
        clause explorer
      </h1>
      <p style={{ color: 'var(--ink-subtle)', marginTop: 4 }}>
        comparable-deals workbench
      </p>

      <section
        aria-label="stack health"
        style={{
          marginTop: 'var(--pad-lg)',
          border: '1px solid var(--hairline)',
          borderRadius: 'var(--radius)',
          background: 'var(--surface-1)',
          padding: 'var(--pad-md)',
          maxWidth: 420,
        }}
      >
        {error && <div style={{ color: 'var(--ink-subtle)' }}>api unreachable ({error})</div>}
        {!error && !health && <div style={{ color: 'var(--ink-subtle)' }}>checking…</div>}
        {health && (
          <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 16px', margin: 0 }}>
            {(['status', 'db', 'cube', 'version'] as const).map((k) => (
              <div key={k} style={{ display: 'contents' }}>
                <dt style={{ color: 'var(--ink-subtle)' }}>{k}</dt>
                <dd style={{ margin: 0, color: 'var(--ink)' }}>{health[k]}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </main>
  )
}

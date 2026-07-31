import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { SHORTCUTS, TABS, type TabId } from './tabs'
import { Coverage } from './views/Coverage'
import { Admin } from './views/Admin'
import { Label } from './views/Label'
import { DealTerms } from './views/DealTerms'
import { Explore } from './views/Explore'
import { useKeyboard } from './useKeyboard'
import './styles/shell.css'

type Health = { status: string; db: string; cube: string; version: string }

/**
 * Shell for the six views. Panels are placeholders until their own issues land (#19–#22,
 * #29–#31); what ships here is the navigation, the keyboard contract and the health strip.
 */
export function App() {
  const [active, setActive] = useState<TabId>('explore')
  const [showHelp, setShowHelp] = useState(false)
  // the matter ids Explore currently shows — the set Deal Terms (#21) rolls up
  const [selection, setSelection] = useState<string[]>([])
  // a Coverage cell click pre-filters Explore; Explore consumes and clears it
  const [coverageSeed, setCoverageSeed] = useState<{ folio_industry_code: string; folio_industry_label: string; signing_year: string } | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetch('/api/healthz')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setHealth)
      .catch(() => setHealthError(true))
  }, [])

  const focusSearch = useCallback(() => searchRef.current?.focus(), [])

  const handlers = useMemo(() => {
    const map: Record<string, () => void> = {
      '/': focusSearch,
      '?': () => setShowHelp(true),
      Escape: () => setShowHelp(false),
    }
    // Number keys map to tab index — see the ordering note in tabs.ts
    TABS.forEach((tab, i) => {
      map[String(i + 1)] = () => setActive(tab.id)
    })
    return map
  }, [focusSearch])

  useKeyboard(handlers)

  const activeTab = TABS.find((t) => t.id === active)!

  return (
    <div className="shell">
      <header className="shell__bar">
        <div className="shell__brand">clause explorer</div>

        <nav className="shell__tabs" role="tablist" aria-label="views">
          {TABS.map((tab, i) => (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={tab.id === active}
              aria-controls={`panel-${tab.id}`}
              className={`shell__tab${tab.id === active ? ' is-active' : ''}`}
              onClick={() => setActive(tab.id)}
            >
              {tab.label}
              <span className="shell__tabkey" aria-hidden="true">
                {i + 1}
              </span>
            </button>
          ))}
        </nav>

        {active !== 'explore' && (
          <input
            ref={searchRef}
            type="search"
            className="shell__search"
            placeholder="search  /"
            aria-label="search"
          />
        )}
      </header>

      <main
        className="shell__main"
        role="tabpanel"
        id={`panel-${active}`}
        aria-label={activeTab.label}
      >
        <h1 className="shell__title">{activeTab.label}</h1>
        <p className="shell__hint">{activeTab.hint}</p>
        {active === 'explore' ? (
          // The selection lives here, not inside Explore: switching tabs unmounts the view, and
          // Deal Terms must roll up the set the partner actually chose rather than defaulting
          // to the whole corpus.
          <Explore
            searchRef={searchRef}
            onSelectionChange={setSelection}
            seedFilters={coverageSeed}
            onSeedConsumed={() => setCoverageSeed(null)}
          />
        ) : active === 'deal-terms' ? (
          <DealTerms selection={selection} />
        ) : active === 'coverage' ? (
          <Coverage
            onNavigateToExplore={(filters) => {
              setCoverageSeed(filters)
              setActive('explore')
            }}
          />
        ) : active === 'label' ? (
          <Label />
        ) : active === 'admin' ? (
          <Admin />
        ) : (
          <p className="shell__pending">
            This view lands in its own issue. The shell, keyboard contract and health strip are
            what ship here.
          </p>
        )}
      </main>

      <footer className="shell__status">
        {healthError && (
          <>
            <span className="shell__dot shell__dot--bad" />
            <span>api unreachable</span>
          </>
        )}
        {health && (
          <>
            <span
              className={`shell__dot ${
                health.status === 'ok' ? 'shell__dot--ok' : 'shell__dot--warn'
              }`}
            />
            <span>{health.status}</span>
            <span className="shell__sep">·</span>
            <span>db {health.db}</span>
            <span className="shell__sep">·</span>
            <span>cube {health.cube}</span>
            <span className="shell__sep">·</span>
            <span>v{health.version}</span>
          </>
        )}
        <span className="shell__spacer" />
        <button type="button" className="shell__helpbtn" onClick={() => setShowHelp(true)}>
          ? shortcuts
        </button>
      </footer>

      {showHelp && (
        <div className="shell__scrim" onClick={() => setShowHelp(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            className="shell__dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="shell__dialogtitle">Keyboard shortcuts</h2>
            <dl className="shell__keys">
              {SHORTCUTS.map(([key, what]) => (
                <div key={key} className="shell__keyrow">
                  <dt>
                    <kbd>{key}</kbd>
                  </dt>
                  <dd>{what}</dd>
                </div>
              ))}
            </dl>
            <button type="button" className="shell__close" onClick={() => setShowHelp(false)}>
              close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

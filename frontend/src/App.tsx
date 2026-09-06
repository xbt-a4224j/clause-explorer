import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { SHORTCUTS, TABS, type TabId } from './tabs'
import { ignoreAbort } from './abort'
import type { Journey, JourneySeed } from './journeys'
import { Trust } from './views/Trust'
import { Ask } from './views/Ask'
import { Label } from './views/Label'
import { Overview } from './views/Overview'
import { DealTerms } from './views/DealTerms'
import { Explore } from './views/Explore'
import { useKeyboard } from './useKeyboard'
import './styles/shell.css'

type Health = { status: string; db: string; cube: string; version: string }

/**
 * Shell for the views. Landing tab is Overview (#39) — it states what the system is before
 * any view demonstrates it; Explore, the demo entry point, is one key away.
 */
export function App() {
  const [active, setActive] = useState<TabId>('overview')
  const [showHelp, setShowHelp] = useState(false)
  // the matter ids Explore currently shows — the set Deal Terms (#21) rolls up
  const [selection, setSelection] = useState<string[]>([])
  // An Overview journey pre-filters Explore; Explore consumes and clears it. The journey now
  // starts on Ask (#48), so the seed can outlive a tab switch — it is applied whenever Explore
  // next mounts, which is the journey's second step. Arrive already narrowed rather than at an
  // empty search box.
  const [seed, setSeed] = useState<JourneySeed | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState(false)
  // What is typed in the header box on any tab but Explore. It had no state and no handler:
  // `?` advertised "/ focus search", the box rendered on five of six tabs, and typing into it
  // did nothing at all. A prominent control that does nothing costs a first-time user their
  // first attempt.
  const [search, setSearch] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // #38: the shell outlives every tab, but it is still the one place a failed abort would
    // be invisible — the app root unmounts only in tests, which is exactly where it mattered
    const controller = new AbortController()
    fetch('/api/healthz', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setHealth)
      .catch(ignoreAbort(() => setHealthError(true)))
    return () => controller.abort()
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
            <span key={tab.id} className="shell__tabslot">
              {/* The divider marks where the product ends and the evidence for it begins. It read
                  "under the hood", which means implementation detail you may skip — the opposite
                  of true here, since Trust is where a data owner decides whether to believe any
                  of the four tabs to its left. */}
              {tab.group === 'under-the-hood' && TABS[i - 1]?.group === 'work' && (
                <span className="shell__tabgroup" aria-hidden="true">
                  evidence
                </span>
              )}
              <button
                role="tab"
                type="button"
                aria-selected={tab.id === active}
                aria-controls={`panel-${tab.id}`}
                className={`shell__tab shell__tab--${tab.group}${tab.id === active ? ' is-active' : ''}`}
                onClick={() => setActive(tab.id)}
              >
                {tab.label}
                <span className="shell__tabkey" aria-hidden="true">
                  {i + 1}
                </span>
              </button>
            </span>
          ))}
        </nav>

        {active !== 'explore' && (
          <input
            ref={searchRef}
            type="search"
            className="shell__search"
            placeholder="search Explore  /"
            aria-label="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter' || !search.trim()) return
              // Explore is where searching this corpus happens, so the box goes there rather
              // than growing a second search of its own. The seed is the existing way one tab
              // hands a starting point to another.
              setSeed({
                folio_industry_code: null,
                folio_industry_label: null,
                signing_year: null,
                consideration_type: null,
                description: search,
              })
              setActive('explore')
              setSearch('')
            }}
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
        {active === 'overview' ? (
          <Overview
            onStartJourney={(journey: Journey) => {
              if (journey.seed) setSeed(journey.seed)
              setActive(journey.tab)
            }}
          />
        ) : active === 'explore' ? (
          // The selection lives here, not inside Explore: switching tabs unmounts the view, and
          // Deal Terms must roll up the set the partner actually chose rather than defaulting
          // to the whole corpus.
          <Explore
            searchRef={searchRef}
            onSelectionChange={setSelection}
            seedFilters={seed}
            onSeedConsumed={() => setSeed(null)}
          />
        ) : active === 'deal-terms' ? (
          <DealTerms selection={selection} />
        ) : active === 'label' ? (
          <Label />
        ) : active === 'trust' ? (
          <Trust />
        ) : active === 'ask' ? (
          <Ask />
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

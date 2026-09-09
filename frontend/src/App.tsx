import { useEffect, useRef, useState } from 'react'
import type { TabId } from './tabs'
import { Explore, Label, Rollup, RollupDiagram, Shell, Trust, ignoreAbort } from '@semantic-explorer-base/ui'
import type { Ablation } from '@semantic-explorer-base/ui'
import type { JourneySeed, ShellStatus } from '@semantic-explorer-base/ui'
import type { Journey } from './journeys'
import { Ask } from './views/Ask'
import { Overview } from './views/Overview'
// How this corpus draws a record: `target ← acquirer`, the inferred-industry chip, the date.
// The card owns everything else — expansion, scores, drill-through, the provenance line.
import { RECORD_RENDERERS } from './recordRenderers'
import { EXPLORE_RANKERS, describeExploreQuery, toExploreRequestFilters } from './exploreRequest'
import { STRINGS } from './strings'
import { corpusStrip } from './corpusStrip'
import './styles/shell.css'

type Health = { status: string; db: string; cube: string; version: string }

/**
 * Shell for the views. Landing tab is Overview (#39) — it states what the system is before
 * any view demonstrates it.
 *
 * The frame itself — bar, tabs, status strip — moved to the platform's `Shell`
 * (semantic-explorer-base#8). What stays here: which view renders per tab, this app's health
 * check, and what pressing Enter in the search box actually does.
 */
/**
 * What each prompt change bought, measured 2026-09-06 under shape-aware grading.
 *
 * These are the rows from `docs/results/ask-strategies.md`, not a summary of them. The tab
 * could previously report only a headline, which was the wrong output twice over: the first
 * headline published here (23/24) came from a metric that graded the deal point and ignored the
 * SHAPE, so a run that picked the right term and then returned the corpus size scored as
 * correct. Re-graded honestly the same prompt scored 7 of 27, and everything above that came
 * from two specific decisions rather than from the model getting better.
 *
 * The shipped row is deliberately not the top score. Naming the missing terms in the prompt
 * would score higher and would be overfitting to this question set.
 */
const ASK_ABLATION: Ablation = {
  outOf: 27,
  answerableOutOf: 20,
  steps: [
    { label: 'free choice over 11 measures', score: 4, answerable: 1 },
    { label: 'as first shipped (shape-aware grading)', score: 7, answerable: 5 },
    { label: 'drop the coverage shape', score: 8, answerable: 6 },
    { label: 'name distribution the default, list its phrasings', score: 17, answerable: 15 },
    { label: 'decline when the computation is inexpressible', score: 20, answerable: 16 },
    {
      label: 'list each deal point with the answers it takes',
      score: 23,
      answerable: 17,
      shipped: true,
    },
  ],
  misses: (
    <>
      <strong>Still wrong at 23 of 27:</strong> one deal-point confusion (ordinary course efforts
      standard read as buyer consent requirement), two median-versus-distribution mixups, and one
      of the seven questions that should have been declined.
    </>
  ),
  provenance: (
    <>
      One trial per row, <code>gpt-4o-mini</code> at temperature 0, which is not determinism:
      three identical runs of the same prompt scored 23, 21 and 22. A single run is a sample. The
      questions were also written by the same person who tuned the prompt against them, which
      makes this a smoke test with an answer key rather than a benchmark. Harness{' '}
      <code>backend/explorer/evals/ask_bench.py</code>, answer key{' '}
      <code>docs/eval/ask_questions.json</code>.
    </>
  ),
}

export function App() {
  const [active, setActive] = useState<TabId>('overview')
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

  const status: ShellStatus | null = healthError
    ? { ok: false, label: 'api unreachable' }
    : health
      ? {
          ok: health.status === 'ok',
          label: health.status,
          items: [`db ${health.db}`, `cube ${health.cube}`, `v${health.version}`],
        }
      : null

  return (
    <Shell
      brand="clause explorer"
      strings={STRINGS}
      activeId={active}
      onSelect={setActive}
      status={status}
      search={
        active === 'explore'
          ? undefined
          : {
              placeholder: 'search Explore',
              value: search,
              onChange: setSearch,
              inputRef: searchRef,
              // Explore is where searching this corpus happens, so the box goes there rather
              // than growing a second search of its own. The seed is the existing way one tab
              // hands a starting point to another.
              // No filters: a text search should not silently narrow by anything the user
              // did not ask for. `filters` absent clears them all on arrival.
              onSubmit: (value) => {
                setSeed({ description: value })
                setActive('explore')
                setSearch('')
              },
            }
      }
    >
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
          strings={STRINGS}
          corpusStrip={corpusStrip(STRINGS.glossary)}
          render={RECORD_RENDERERS}
          searchRef={searchRef}
          onSelectionChange={setSelection}
          seedFilters={seed}
          onSeedConsumed={() => setSeed(null)}
          toRequestFilters={toExploreRequestFilters}
          describeQuery={describeExploreQuery}
          rankers={EXPLORE_RANKERS}
        />
      ) : active === 'terms' ? (
        <Rollup
          selection={selection}
          strings={STRINGS}
          scopeFallback="Comparable PUBLIC deals from the MAUD study of SEC-filed merger agreements — not this firm's own matter history."
          diagram={
            <RollupDiagram
              description={
                '152 merger agreements were each read by lawyers who answered the same 92 ' +
                "questions, the American Bar Association's public target deal points. Those " +
                'answers are stored one row per agreement per question, which is why a new ' +
                'question costs nothing to add. Selecting a set of deals in Explore rolls ' +
                'those rows up into a count per question. Below a sample size of 30 the ' +
                'answer renders as a count rather than a percentage, and every row drills ' +
                'back to the clause language in the source file.'
              }
            />
          }
        />
      ) : active === 'label' ? (
        <Label strings={STRINGS} />
      ) : active === 'trust' ? (
        <Trust
          strings={STRINGS}
          ablation={ASK_ABLATION}
          accuracyChartCopy={({ heldOut, reportable, total }) => ({
            title: 'Which questions could run without a lawyer?',
            note: (
              <>
                Each bar is one of the ABA&rsquo;s deal-point questions; its length is how often
                an automated extractor got it right on {heldOut} agreements lawyers had already
                answered. Point it at documents nobody has annotated and{' '}
                <strong>
                  {reportable} of {total} questions could be answered by machine
                </strong>
                . For the other {total - reportable}, a person has to read the agreement.
              </>
            ),
          })}
        />
      ) : (
        <Ask />
      )}
    </Shell>
  )
}

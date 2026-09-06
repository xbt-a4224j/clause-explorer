import { useEffect, useState } from 'react'
import type { CatalogEntry, CatalogResponse } from '../types'
import { ignoreAbort } from '../abort'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { RoutingDiagram } from '../components/RoutingDiagram'
import { QueryBuilder } from '../components/QueryBuilder'
import { AskBox } from '../components/AskBox'
import { SessionCost } from '../components/SessionCost'
import { Term } from '../components/Term'
import { Grading } from '../components/Grading'

/**
 * Ask (#36, renamed from Semantic Layer in #48).
 *
 * The product's central engineering claim lived only in the README: an agent answering
 * analytical questions has two independent ways to be wrong — the number, and the
 * *definition* of the number. This tab makes that inspectable.
 *
 * The old name described the mechanism rather than the act. This is where a question becomes
 * a governed selection you can confirm, so it is named for what happens here and sits second
 * in the bar. The semantic-layer argument is unchanged and still on the tab — it moved below
 * the demonstration, which is where an argument belongs once the thing it argues for is on
 * screen.
 *
 * The vocabulary is read live from Cube rather than checked in. A stale copy could disagree
 * with `cube/model/*.yml`, and then any selection failure becomes an unfalsifiable argument
 * about which list was authoritative.
 *
 * #47 put the model on this tab. Free text goes to `select_via_llm`, which returns a
 * selection — never an answer, never a number — rendered as chips a person confirms before
 * `/agent/run-selection` computes anything. Until that landed, nothing a user could touch
 * called a model at all, and the repo's central claim was reachable only from the eval
 * harness. The catalog, the builder and the offline grade below it still need no key; the
 * question box does, and 7bc47ee dropped the guarantee that it would not.
 */

/**
 * The vocabulary, grouped by the job each name does.
 *
 * It was two columns headed Measures and Dimensions, each a stack of 3-6 line paragraphs. That
 * is Cube's own filing system, and it answers a question nobody asked: a reader wants to know
 * what they can ASK, and "is this a measure or a dimension" is an implementation detail of the
 * semantic layer. Twenty-nine paragraphs under two headings is also just a wall — everything
 * looked equally important, including `deal_points.id`.
 *
 * The descriptions themselves are written AT THE MODEL — "ALWAYS filter on this before reading
 * any count" — which is correct for the thing that reads /meta and wrong for a person reading a
 * page. So the lead line is trimmed to the first sentence and the rest sits behind one toggle
 * for the whole panel. Nothing is hidden; it is ordered.
 */

const GROUPS: { title: string; blurb: string; match: (name: string) => boolean }[] = [
  {
    title: 'Count agreements',
    blurb: 'Sample sizes. Every figure this product reports carries one of these.',
    match: (n) =>
      /\.(n|count_distinct_matters|expert_labelled_n|numeric_n|with_source_span_n)$/.test(n),
  },
  {
    title: 'Count provisions',
    blurb: 'How many agreements in the slice actually have the thing.',
    match: (n) => n.endsWith('.present_count'),
  },
  {
    title: 'Numbers inside answers',
    blurb:
      'For terms measured in days, months or percent. Pin one deal point first — unscoped these mix the units.',
    match: (n) => /(median|p25|p75)_numeric_value$/.test(n),
  },
  {
    title: 'Choose the term',
    blurb: 'Which negotiated point, and how it came out. Nearly every legal question names one.',
    match: (n) => /\.(deal_point_name|position|numeric_value)$/.test(n),
  },
  {
    title: 'Choose the deals',
    blurb: 'Narrow the set of agreements before asking about a term.',
    match: (n) =>
      /comparable_deals\.(label|code|consideration_type|signing_year|signing_date|deal_size_band|target_name|acquirer_name)$/.test(
        n,
      ),
  },
  {
    title: 'Provenance and plumbing',
    blurb: 'Row identity and how a value got there. Rarely what a question is about.',
    match: () => true,
  },
]

/**
 * Split a Cube description into its shouted role label and its first real sentence.
 *
 * The model-facing descriptions open with a flag in capitals — `THE DENOMINATOR.`,
 * `THE NUMERATOR for ...` — which is genuinely the most useful thing about the measure, so it
 * becomes a tag rather than being thrown away. Discarding it left sentences starting with a
 * dangling em dash: "— how many answers in the selection carry a number at all."
 *
 * `e.g.` and `i.e.` are not sentence ends. Treating them as one truncated four entries to
 * "The ABA deal point being answered, e.g." and "The median of the numeric answers — e.g.".
 */
export function summarise(description: string): { role: string | null; lead: string } {
  if (!description) return { role: null, lead: '' }
  // At least TWO capitalised words, so a description opening on a single one — `FALSE for
  // MAUD's expert labels` — is prose rather than a label. Terminated by a full stop, a colon,
  // an em dash, or the first lowercase word: `THE DENOMINATOR FOR EVERY PERCENTILE BELOW —`
  // ends on the dash and `THE NUMERATOR for "how many..."` ends on `for`.
  const labelled = description.match(
    /^([A-Z][A-Z_]*(?:[ /][A-Z][A-Z_]*)+)(?:\s*[.:—–-]|\s+(?=[a-z]))\s*(.*)$/s,
  )
  const role = labelled ? labelled[1].trim() : null
  let rest = (labelled ? labelled[2] : description).trim()
  rest = rest.replace(/^[—–-]\s*/, '')
  // Only when a label was actually removed, and never on an identifier: blanket capitalising
  // turned `percentile_cont(0.5) WITHIN GROUP` into `Percentile_cont(...)`.
  const code = /^[a-z_]+[_(]/.test(rest)
  if (labelled && rest && !code) rest = rest[0].toUpperCase() + rest.slice(1)

  // a full stop that ends a sentence: followed by a space and a capital, or the string's end,
  // and not part of e.g. / i.e. / an initial
  // A sentence may open with a digit or a quote — "809 of 12,937 rows." and '"Type of
  // Consideration-Answer".' both follow one. The required whitespace is what keeps `0.5` and
  // `12,937` from splitting: there is no space after those stops.
  const end = rest.search(/(?<!\b(?:e\.g|i\.e|[A-Z]))\.(?=\s+["'(0-9A-Z]|$)/)
  const lead = end > 0 ? rest.slice(0, end + 1) : rest
  return { role, lead }
}

function EntryList({
  entries,
  testId,
  full,
}: {
  entries: CatalogEntry[]
  testId: string
  full: boolean
}) {
  const seen = new Set<string>()
  const groups = GROUPS.map((g) => {
    const rows = entries.filter((e) => !seen.has(e.name) && g.match(e.name))
    rows.forEach((r) => seen.add(r.name))
    return { ...g, rows }
  }).filter((g) => g.rows.length)

  return (
    <div className="cat" data-testid={testId}>
      {groups.map((g) => (
        <section className="cat__group" key={g.title}>
          <h4 className="cat__grouph">
            {g.title} <span className="cat__count">{g.rows.length}</span>
          </h4>
          <p className="cat__blurb">{g.blurb}</p>
          <ul className="cat__list">
            {g.rows.map((e) => (
              <li className="cat__item" key={e.name}>
                <code className="cat__name">{e.name.split('.')[1]}</code>
                <span className="cat__cube">{e.name.split('.')[0]}</span>
                <span className="cat__desc">
                  {full ? (
                    e.description
                  ) : (
                    <>
                      {summarise(e.description || '').role && (
                        <span className="cat__role">
                          {summarise(e.description || '').role}
                        </span>
                      )}
                      {summarise(e.description || '').lead}
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

export function Ask() {
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  // #50: the running total lives on the tab rather than inside the box, so it stays put while
  // the box is cleared and re-asked. Accumulated from the same measured `usage` payloads the
  // per-question line renders.
  const [questions, setQuestions] = useState(0)
  const [sessionCost, setSessionCost] = useState(0)
  const [vocabularyOpen, setVocabularyOpen] = useState(false)
  const [fullNotes, setFullNotes] = useState(false)

  useEffect(() => {
    // #38
    const controller = new AbortController()
    fetch('/api/agent/catalog', { signal: controller.signal })
      .then(async (r) => {
        const body = await r.json()
        if (!r.ok) throw new Error(body?.detail ?? 'The semantic layer did not answer.')
        return body as CatalogResponse
      })
      .then(setCatalog)
      .catch(ignoreAbort((e) => setError(e.message)))
    return () => controller.abort()
  }, [])

  if (error) {
    // Distinct from an empty vocabulary on purpose: "the model may select nothing" is a
    // different and much worse claim than "Cube is unreachable".
    return (
      <div className="state state--error">
        <h3 className="state__title">Semantic layer unavailable</h3>
        <p className="state__body">{error}</p>
        <p className="state__body">
          The vocabulary is read live from Cube, so it cannot be shown from cache without
          risking a catalog that disagrees with the models it claims to describe.
        </p>
      </div>
    )
  }

  if (!catalog) return <div className="skeleton skeleton--row" aria-label="loading catalog" />

  return (
    <div className="sem">
      <p className="sem__pointer">
        Assemble a question here and run it: a measure and a slice from the governed vocabulary,
        the exact selection that will be sent, and a number with its sample size — or a refusal.
        If you came to find comparable deals, that is <strong>Explore</strong>.
      </p>

      {/* #47: the free-text path sits above the click-built one. A reader who lands here should
          meet the model first — it is the thing the repo claims and the thing that was, until
          now, reachable only from the eval harness. The builder below is the contrast.

          It also sits above the vocabulary now. The catalog is reference material and it was
          the first screen and a half of this tab: a visitor met 48 identifiers and their
          paragraphs before reaching the box they came to type in. */}
      <section className="sem__pane">
        <AskBox
          onAsked={(costUsd) => {
            setQuestions((n) => n + 1)
            setSessionCost((total) => total + costUsd)
          }}
        />
      </section>

      <section className="sem__pane" data-testid="catalog">
        <h3 className="sem__h">The vocabulary a selection may draw from</h3>
        <p className="sem__sub">
          Read from Cube&rsquo;s metadata endpoint on every request.{' '}
          <span data-testid="label-space">
            Label space: <span className="mono">{catalog.label_space}</span>
          </span>{' '}
          — <span className="mono">{catalog.measures.length}</span> measures and{' '}
          <span className="mono">{catalog.dimensions.length}</span> dimensions. The model chooses
          from these names and no others, and an offline eval grades against exactly this list.
        </p>

        {/* The count is the claim and stays on screen; the names behind it are reference, and
            reference belongs one click away rather than in front of the instrument. */}
        <button
          type="button"
          className="viz__toggle"
          aria-expanded={vocabularyOpen}
          data-testid="catalog-toggle"
          onClick={() => setVocabularyOpen((open) => !open)}
        >
          {vocabularyOpen ? 'hide' : 'show'} all {catalog.label_space} names, with what each one
          counts
        </button>

        {vocabularyOpen && (
          <div data-testid="catalog-list">
            <label className="cat__fulltoggle">
              <input
                type="checkbox"
                checked={fullNotes}
                onChange={(e) => setFullNotes(e.target.checked)}
                data-testid="catalog-full"
              />
              show the full note on each name
            </label>
            {/* Measures and dimensions are interleaved on purpose: they are grouped by the job
                a name does, and "count the agreements" needs one of each. */}
            <EntryList
              entries={[...catalog.measures, ...catalog.dimensions]}
              testId="catalog-entries"
              full={fullNotes}
            />
          </div>
        )}
      </section>

      <section className="sem__pane">
        <QueryBuilder measures={catalog.measures} dimensions={catalog.dimensions} />
      </section>

      <Grading />

      <section className="sem__pane">
        <h3 className="sem__h">The comparison — what the other route looks like</h3>
        <p className="sem__sub" data-testid="freeform-note">
          The freeform text-to-SQL arm is shown for contrast and is not run. Its SQL is often
          right; it has no table like the one above, because two generated queries can be diffed
          against each other but not scored.
        </p>
        <div className="sem__cols">
          <div>
            <h4 className="sem__h4">Governed selection — what this app sends</h4>
            <pre className="qb__json">{`{
  "measures": ["deal_points.median_numeric_value"],
  "dimensions": [],
  "filters": [{
    "member": "deal_points.deal_point_name",
    "operator": "equals",
    "values": ["Initial matching rights period (COR)-Answer"]
  }]
}`}</pre>
            <p className="qb__hint">
              Four names, all from the catalog. Wrong or right is one comparison against an
              expected selection — which is the table above.
            </p>
          </div>
          <div>
            <h4 className="sem__h4">Freeform text-to-SQL — the usual approach</h4>
            <pre className="qb__json">{`SELECT percentile_cont(0.5) WITHIN GROUP (
         ORDER BY numeric_value)
FROM deal_points
WHERE deal_point_name =
  'Initial matching rights period (COR)-Answer'
  AND numeric_value IS NOT NULL;`}</pre>
            <p className="qb__hint">
              Plausible, and probably right. But <code>avg</code> instead of{' '}
              <code>percentile_cont</code> would look just as plausible and return a different
              number — and grading that means diffing free text against free text.
            </p>
          </div>
        </div>
      </section>

      {/*
        #48: the argument, verbatim, below the demonstration rather than in front of it. The
        panel id is the localStorage key and deliberately unchanged by the rename — a reader
        who opened this explainer keeps it open.
      */}
      <ExplainerPanel
        id="semantic-layer"
        title="What the semantic layer is for"
        diagram={<RoutingDiagram />}
      >
        <p>
          <strong>What this tab is for.</strong> Showing what the language model is and is not
          allowed to do. It <em>routes</em>: it picks a measure and
          filters from the published vocabulary above, and Postgres computes every number on
          this screen. Correctness is then one discrete question — did it pick the right
          measure and filters — gradeable offline with no database and no model. It also gives{' '}
          <Term>min_n</Term> somewhere to stand: the gate applies to the resolved query, whoever
          assembled it.{' '}
          <span data-testid="keyless-note">
            The catalog, the builder and the grade need no API key. The question box above does
            — it is the one thing here that calls a model, which is the point of it.
          </span>
        </p>
        <p data-testid="relocated-risk">
          <strong>The limit.</strong> The risk moves, it does not disappear: a{' '}
          <em>wrong selection returns a real number for the wrong question</em>, which is harder
          to spot than an obvious error. The only mitigation is the resolved query line shown
          above every answer, which puts the interpretation in front of the one person qualified
          to catch it.
        </p>
      </ExplainerPanel>

      {/* #50: the foot of the tab, so it accumulates behind everything else rather than
          competing with the answer for attention. */}
      <SessionCost questions={questions} costUsd={sessionCost} />
    </div>
  )
}

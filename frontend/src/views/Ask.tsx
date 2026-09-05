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

function EntryList({ entries, testId }: { entries: CatalogEntry[]; testId: string }) {
  return (
    <ul className="cat__list" data-testid={testId}>
      {entries.map((e) => (
        <li className="cat__item" key={e.name}>
          <code className="cat__name">{e.name}</code>
          <span className="cat__type">{e.type}</span>
          {e.description && <p className="cat__desc">{e.description}</p>}
        </li>
      ))}
    </ul>
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

      <section className="sem__pane" data-testid="catalog">
        <h3 className="sem__h">The vocabulary a selection may draw from</h3>
        <p className="sem__sub">
          Read live from Cube&rsquo;s metadata endpoint, not a checked-in copy.{' '}
          <span data-testid="label-space">
            Label space: <span className="mono">{catalog.label_space}</span>
          </span>{' '}
          — the model chooses from these names and no others, and an offline eval grades
          against exactly this list.
        </p>

        <div className="sem__cols">
          <div>
            <h4 className="sem__h4">
              Measures <span className="mono">{catalog.measures.length}</span>
            </h4>
            <EntryList entries={catalog.measures} testId="catalog-measures" />
          </div>
          <div>
            <h4 className="sem__h4">
              Dimensions <span className="mono">{catalog.dimensions.length}</span>
            </h4>
            <EntryList entries={catalog.dimensions} testId="catalog-dimensions" />
          </div>
        </div>
      </section>

      {/* #47: the free-text path sits above the click-built one. A reader who lands here should
          meet the model first — it is the thing the repo claims and the thing that was, until
          now, reachable only from the eval harness. The builder below is the contrast. */}
      <section className="sem__pane">
        <AskBox
          onAsked={(costUsd) => {
            setQuestions((n) => n + 1)
            setSessionCost((total) => total + costUsd)
          }}
        />
      </section>

      <section className="sem__pane">
        <QueryBuilder measures={catalog.measures} dimensions={catalog.dimensions} />
      </section>

      <Grading />

      <section className="sem__pane">
        <h3 className="sem__h">The comparison — what the other route looks like</h3>
        <p className="sem__sub" data-testid="freeform-note">
          The freeform text-to-SQL arm is shown for contrast and{' '}
          <strong>deliberately not run</strong>. The point is not that its SQL is wrong — it
          is often right. The point is that there is no table like the one above for it: two
          generated queries can be diffed against each other, never scored, so nothing tells
          you whether the system is getting better.
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
          allowed to do. It is a <em>router</em>, not a calculator: it picks a measure and
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

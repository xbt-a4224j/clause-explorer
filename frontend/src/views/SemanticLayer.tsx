import { useEffect, useState } from 'react'
import type { CatalogEntry, CatalogResponse } from '../types'
import { ExplainerPanel } from '../components/ExplainerPanel'
import { RoutingDiagram } from '../components/RoutingDiagram'
import { QueryBuilder } from '../components/QueryBuilder'
import { Term } from '../components/Term'
import { Grading } from '../components/Grading'

/**
 * Semantic Layer (#36).
 *
 * The product's central engineering claim lived only in the README: an agent answering
 * analytical questions has two independent ways to be wrong — the number, and the
 * *definition* of the number. This tab makes that inspectable.
 *
 * The vocabulary is read live from Cube rather than checked in. A stale copy could disagree
 * with `cube/model/*.yml`, and then any selection failure becomes an unfalsifiable argument
 * about which list was authoritative.
 *
 * Keyless by design: the catalog, the routing argument and the refusal behaviour are all
 * database-and-model-free. Only live selection needs a key, and its absence is a designed
 * state rather than a broken tab.
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

export function SemanticLayer() {
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/agent/catalog')
      .then(async (r) => {
        const body = await r.json()
        if (!r.ok) throw new Error(body?.detail ?? 'The semantic layer did not answer.')
        return body as CatalogResponse
      })
      .then((d) => !cancelled && setCatalog(d))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
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
      <ExplainerPanel
        id="semantic-layer"
        title="What the semantic layer is for"
        diagram={<RoutingDiagram />}
      >
        <p>
          <strong>What this tab is for.</strong> Showing what the language model is and is not
          allowed to do. Ask a question in plain English and something has to decide which
          number answers it. The model makes that decision — it is a <em>router</em>, not a
          calculator. Every number on this screen is computed by Postgres.
        </p>
        <p>
          <strong>Why that is worth the trouble.</strong> If the model writes SQL freely, it
          picks both the answer and the definition of the answer, and you are left comparing
          two plausible queries with no way to score either. Constraining it to a published
          vocabulary makes correctness a single discrete question: did it pick the right
          measure and filters? That is gradeable offline — no database, no model. The same
          discipline gives <Term>min_n</Term> somewhere to stand: the gate is applied to the
          resolved query, whoever assembled it.
        </p>
        <p data-testid="relocated-risk">
          <strong>What this does not fix.</strong> The risk moves; it does not disappear. A{' '}
          <em>wrong selection returns a real number for the wrong question</em>, which is
          harder to spot than an obvious error. The mitigation is the resolved query line
          shown above every answer, which puts the interpretation in front of the one person
          qualified to catch it.
        </p>
        <p data-testid="keyless-note">
          <strong>No API key needed for any of this.</strong> The vocabulary, the routing
          argument and the refusal behaviour are all keyless. A key is needed only to run a
          live selection. The measures are defined over <Term>MAUD</Term>&rsquo;s expert
          annotations, so the numbers are lawyer-labelled data, not model output.
        </p>
      </ExplainerPanel>

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
    </div>
  )
}

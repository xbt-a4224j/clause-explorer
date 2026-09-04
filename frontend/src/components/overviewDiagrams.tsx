/**
 * The two Overview diagrams (#39, trimmed in #45).
 *
 * Deliberately NOT another drawing of the routing argument — that lives in `RoutingDiagram`
 * under Semantic Layer, and two diagrams making the same claim would invite the reader to
 * look for a difference that is not there. These answer the two questions the other tabs
 * assume you have already asked: what is the shape of the system, and where does a displayed
 * figure come from.
 *
 * `HybridRetrievalDiagram` was the third. #45 cut the paragraph it illustrated — the min-max
 * normalization argument — down to nothing on this tab, and a diagram whose prose no longer
 * exists is an orphan. The argument itself moved to `docs/walkthrough.md`, and the property it
 * claimed is still asserted by `backend/tests/test_hybrid_retrieval.py`.
 *
 * Token-only like every other diagram here, so they cannot drift from the palette, and
 * sized by viewBox so they scale with the panel.
 */

function Arrow({ id }: { id: string }) {
  return (
    <marker
      id={id}
      viewBox="0 0 8 8"
      refX="7"
      refY="4"
      markerWidth="6"
      markerHeight="6"
      orient="auto-start-reverse"
    >
      <path d="M0,0 L8,4 L0,8 z" fill="var(--hairline-strong)" />
    </marker>
  )
}

/**
 * The system in one picture: two ingest sources become one store, the store feeds two
 * independent read paths, and the tabs sit on top of those paths. The point a first-time
 * visitor should take away is that retrieval and the semantic layer are *separate* —
 * finding a document and computing a number are different problems here.
 */
export function SystemDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 208"
      role="img"
      aria-labelledby="ov-system-title"
      aria-describedby="ov-system-desc"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="ov-system-title">How the system is put together</title>
      <desc id="ov-system-desc">
        Merger agreements with expert deal-point labels, and an industry ontology, are ingested into
        Postgres. Two independent read paths run off that store. The retrieval path combines keyword
        and vector search to find comparable matters and clauses. The semantic layer path answers
        aggregate questions: a model selects from a fixed catalog of named measures and Postgres
        computes the figure. The Explore and Tables views sit on the retrieval path; Deal Terms and
        Coverage sit on the semantic layer path. Nothing generates a number from free text.
      </desc>

      <defs>
        <Arrow id="ov-system-arrow" />
      </defs>

      <g className="loop__edges" markerEnd="url(#ov-system-arrow)">
        <path d="M116,36 H152" />
        <path d="M116,84 H152" />
        <path d="M256,60 H292" />
        <path d="M396,44 H432" />
        <path d="M396,124 H432" />
        <path d="M348,76 V124 H432" />
      </g>

      <g className="loop__node">
        <rect x="12" y="16" width="104" height="40" rx="6" />
        <rect x="12" y="64" width="104" height="40" rx="6" />
        <rect x="292" y="24" width="104" height="40" rx="6" />
        <rect x="292" y="104" width="104" height="40" rx="6" />
      </g>

      <g className="loop__node loop__node--key">
        <rect x="152" y="40" width="104" height="40" rx="6" />
      </g>

      <g className="loop__node loop__node--out">
        <rect x="432" y="24" width="140" height="40" rx="6" />
        <rect x="432" y="104" width="140" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="64" y="34">
          merger agreements
        </text>
        <text x="64" y="82">
          industry ontology
        </text>
        <text x="204" y="58">
          Postgres
        </text>
        <text x="344" y="42">
          hybrid retrieval
        </text>
        <text x="344" y="122">
          semantic layer
        </text>
        <text x="502" y="42">
          Explore · Tables
        </text>
        <text x="502" y="122">
          Deal Terms · Coverage
        </text>
      </g>

      <g className="loop__sub">
        <text x="64" y="48">
          + expert labels
        </text>
        <text x="64" y="96">
          FOLIO concepts
        </text>
        <text x="204" y="72">
          one store, versioned ingest
        </text>
        <text x="344" y="56">
          BM25 + vector
        </text>
        <text x="344" y="136">
          named measures → SQL
        </text>
        <text x="502" y="56">
          find the documents
        </text>
        <text x="502" y="136">
          compute the figures
        </text>
      </g>

      <text className="loop__note" x="300" y="176">
        finding a document and computing a number are different problems, on separate paths
      </text>
      <text className="loop__note" x="300" y="192">
        no figure on any tab is generated from free text
      </text>
    </svg>
  )
}

/**
 * Where a displayed figure comes from, and the gate that can stop it being displayed at
 * all. `min_n` is the piece most readers assume is a nicety; it is doing three jobs, and
 * the third is a confidentiality control rather than a statistical one.
 */
export function ProvenanceDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 214"
      role="img"
      aria-labelledby="ov-prov-title"
      aria-describedby="ov-prov-desc"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="ov-prov-title">Where a figure comes from, and when it is withheld</title>
      <desc id="ov-prov-desc">
        Matters and their expert-labelled deal points are rolled up by a named measure defined once
        in the semantic layer. The count of underlying matters travels with the result. A
        minimum-sample gate then decides: above the threshold the figure is shown with its sample
        size attached; below it the system refuses and says the slice is too thin rather than
        showing a number. That threshold does three jobs at once — statistical honesty,
        extraction-confidence gating, and k-anonymity, because an analyst who filters until only one
        matter remains has extracted a single party's negotiated term through the aggregate layer.
      </desc>

      <defs>
        <Arrow id="ov-prov-arrow" />
      </defs>

      <g className="loop__edges" markerEnd="url(#ov-prov-arrow)">
        <path d="M112,44 H148" />
        <path d="M252,44 H288" />
        <path d="M392,44 H428" />
        <path d="M340,64 V116 H428" />
      </g>

      <g className="loop__node">
        <rect x="12" y="24" width="100" height="40" rx="6" />
        <rect x="148" y="24" width="104" height="40" rx="6" />
      </g>

      <g className="loop__node loop__node--key">
        <rect x="288" y="24" width="104" height="40" rx="6" />
      </g>

      <g className="loop__node">
        <rect x="428" y="24" width="144" height="40" rx="6" />
      </g>

      <g className="loop__node loop__node--out">
        <rect x="428" y="96" width="144" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="62" y="42">
          matters
        </text>
        <text x="200" y="42">
          named measure
        </text>
        <text x="340" y="42">
          min_n gate
        </text>
        <text x="500" y="42">
          figure, with its n
        </text>
        <text x="500" y="114">
          refusal
        </text>
      </g>

      <g className="loop__sub">
        <text x="62" y="56">
          + deal points
        </text>
        <text x="200" y="56">
          defined once, versioned
        </text>
        <text x="340" y="56">
          is the slice thick enough?
        </text>
        <text x="500" y="56">
          drills to the clauses
        </text>
        <text x="500" y="128">
          this slice is too thin
        </text>
      </g>

      <text className="loop__note" x="300" y="170">
        min_n does three jobs: statistical honesty, extraction-confidence gating, and k-anonymity
      </text>
      <text className="loop__note" x="300" y="186">
        filter until n = 1 and you have extracted one party&rsquo;s term through the aggregate
      </text>
      <text className="loop__note" x="300" y="202">
        the gap is not a missing feature — it is the finding
      </text>
    </svg>
  )
}

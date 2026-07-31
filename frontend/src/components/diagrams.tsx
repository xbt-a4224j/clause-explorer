/**
 * Per-tab explanatory diagrams (#35).
 *
 * One per tab, all inline SVG on design tokens so they cannot drift from the palette and stay
 * legible at any zoom. Every one is `role="img"` with a title AND a description that carries
 * the same content in words — a diagram that only works visually is not an explanation for
 * everyone, and these are the load-bearing explanation on each tab.
 *
 * Shared classes live in shell.css under the explainer section: .loop__edges, .loop__node,
 * .loop__label, .loop__sub, .loop__note.
 */

function Arrow({ id }: { id: string }) {
  return (
    <defs>
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
    </defs>
  )
}

/** Explore — a query becomes a filtered, ranked set. The join is on the code, not the label. */
export function ExploreDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 200"
      role="img"
      aria-labelledby="dx-t dx-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="dx-t">How a search becomes a set of comparable deals</title>
      <desc id="dx-d">
        What you type is matched against a legal ontology called FOLIO, which resolves it to a
        concept code rather than a display label. That code selects a branch of the industry
        hierarchy, so asking for healthcare also returns medical devices, pharma and providers.
        The matching matters are then ranked by hybrid retrieval — keyword matching blended with
        semantic similarity. Facet counts are live database queries over whatever is left after
        your filters, which is why they change as you narrow.
      </desc>
      <Arrow id="dx-a" />

      <g className="loop__edges" markerEnd="url(#dx-a)">
        <path d="M118,40 H154" />
        <path d="M268,40 H304" />
        <path d="M424,40 H460" />
        <path d="M362,62 V96" />
        <path d="M304,116 H268" />
        <path d="M154,116 H118" />
      </g>

      <g className="loop__node">
        <rect x="12" y="20" width="106" height="40" rx="6" />
        <rect x="154" y="20" width="114" height="40" rx="6" />
        <rect x="304" y="20" width="120" height="40" rx="6" />
        <rect x="460" y="20" width="128" height="40" rx="6" />
        <rect x="304" y="96" width="120" height="40" rx="6" />
        <rect x="118" y="96" width="150" height="40" rx="6" />
        <rect x="12" y="96" width="106" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="65" y="38">what you type</text>
        <text x="211" y="38">FOLIO concept</text>
        <text x="364" y="38">roll up the tree</text>
        <text x="524" y="38">matching matters</text>
        <text x="364" y="114">rank them</text>
        <text x="193" y="114">facet counts</text>
        <text x="65" y="114">the rail</text>
      </g>
      <g className="loop__sub">
        <text x="65" y="52">“healthcare”</text>
        <text x="211" y="52">a CODE, not a label</text>
        <text x="364" y="52">devices · pharma</text>
        <text x="524" y="52">n = 25 of 152</text>
        <text x="364" y="128">keyword + meaning</text>
        <text x="193" y="128">live, over what is left</text>
        <text x="65" y="128">updates as you filter</text>
      </g>

      <text className="loop__note" x="300" y="176">
        joining on the code is the point: a label can drift from “Health Care Industry” to
        “Healthcare” and return zero rows
      </text>
      <text className="loop__note" x="300" y="190">
        — which looks exactly like “we have no comparable deals”
      </text>
    </svg>
  )
}

/** Deal Terms — 92 questions, long table, rollup over your selection. */
export function DealTermsDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 208"
      role="img"
      aria-labelledby="dt-t dt-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="dt-t">How the deal-terms rollup is built</title>
      <desc id="dt-d">
        152 merger agreements were each read by lawyers who answered the same 92 questions, the
        American Bar Association's public target deal points. Those answers are stored one row
        per agreement per question, which is why a new question costs nothing to add. Selecting a
        set of deals in Explore rolls those rows up into a count per question. Below a sample size
        of 30 the answer renders as a count rather than a percentage, and every row drills back
        to the clause language in the source file.
      </desc>
      <Arrow id="dt-a" />

      <g className="loop__edges" markerEnd="url(#dt-a)">
        <path d="M124,44 H160" />
        <path d="M286,44 H322" />
        <path d="M448,44 H484" />
        <path d="M384,66 V102" />
        <path d="M322,122 H286" />
        <path d="M160,122 H124" />
      </g>

      <g className="loop__node">
        <rect x="12" y="24" width="112" height="40" rx="6" />
        <rect x="160" y="24" width="126" height="40" rx="6" />
        <rect x="322" y="24" width="126" height="40" rx="6" />
        <rect x="484" y="24" width="104" height="40" rx="6" />
        <rect x="322" y="102" width="126" height="40" rx="6" />
        <rect x="160" y="102" width="126" height="40" rx="6" />
        <rect x="12" y="102" width="112" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="68" y="42">152 agreements</text>
        <text x="223" y="42">92 ABA questions</text>
        <text x="385" y="42">one row each</text>
        <text x="536" y="42">your selection</text>
        <text x="385" y="120">roll up</text>
        <text x="223" y="120">“6 of 8”</text>
        <text x="68" y="120">click the row</text>
      </g>
      <g className="loop__sub">
        <text x="68" y="56">read by lawyers</text>
        <text x="223" y="56">same set, every deal</text>
        <text x="385" y="56">12,937 rows</text>
        <text x="536" y="56">8 comparables</text>
        <text x="385" y="134">count per question</text>
        <text x="223" y="134">not 75% — n is too small</text>
        <text x="68" y="134">the actual clause text</text>
      </g>

      <text className="loop__note" x="300" y="182">
        absence is a finding: a question no deal answers renders “0 of 8”, it is not dropped from
        the table
      </text>
      <text className="loop__note" x="300" y="196">
        a missing row would read as “not asked”, which is a different and false claim
      </text>
    </svg>
  )
}

/** Coverage — the grid, and the gate. */
export function CoverageDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 214"
      role="img"
      aria-labelledby="cv-t cv-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="cv-t">How the coverage grid decides what it will not answer</title>
      <desc id="cv-d">
        Every deal is placed in a cell by industry and period, producing a fifteen by three grid
        of forty-five cells. Each cell is counted. Cells holding fewer than five deals are marked
        insufficient to characterize and will refuse rather than report a figure. On the current
        corpus thirty-three of forty-five cells refuse and only twelve are reportable. The
        threshold is enforced on the server, so a direct API call is refused too.
      </desc>
      <Arrow id="cv-a" />

      <g className="loop__edges" markerEnd="url(#cv-a)">
        <path d="M120,44 H156" />
        <path d="M282,44 H318" />
        <path d="M444,44 H480" />
      </g>

      <g className="loop__node">
        <rect x="12" y="24" width="108" height="40" rx="6" />
        <rect x="156" y="24" width="126" height="40" rx="6" />
        <rect x="318" y="24" width="126" height="40" rx="6" />
        <rect x="480" y="24" width="108" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="66" y="42">every deal</text>
        <text x="219" y="42">industry × period</text>
        <text x="381" y="42">count each cell</text>
        <text x="534" y="42">n &lt; 5 ?</text>
      </g>
      <g className="loop__sub">
        <text x="66" y="56">152 matters</text>
        <text x="219" y="56">15 × 3 = 45 cells</text>
        <text x="381" y="56">live, not precomputed</text>
        <text x="534" y="56">the gate</text>
      </g>

      {/* the grid, with thin cells marked by pattern not colour alone */}
      <g className="loop__node">
        {[0, 1, 2].map((r) =>
          [0, 1, 2, 3, 4, 5, 6, 7].map((c) => (
            <rect key={`${r}-${c}`} x={130 + c * 42} y={100 + r * 26} width={38} height={22} rx={3} />
          )),
        )}
      </g>
      <g className="loop__node loop__node--out">
        {[
          [0, 1],
          [0, 4],
          [0, 6],
          [1, 0],
          [1, 3],
          [1, 5],
          [1, 7],
          [2, 0],
          [2, 2],
          [2, 3],
          [2, 5],
          [2, 6],
          [2, 7],
        ].map(([r, c]) => (
          <rect key={`x-${r}-${c}`} x={130 + c * 42} y={100 + r * 26} width={38} height={22} rx={3} />
        ))}
      </g>
      <text className="loop__sub" x="60" y="140" textAnchor="middle">
        the grid
      </text>
      <text className="loop__note" x="500" y="128">
        dashed = refuses
      </text>
      <text className="loop__note" x="500" y="142">
        33 of 45
      </text>

      <text className="loop__note" x="300" y="190">
        a gap is more actionable than a strength you already know about — thin cells are styled
        loudly, not faded
      </text>
      <text className="loop__note" x="300" y="204">
        and the same threshold is k-anonymity: filter to n=1 and you have one client’s term
      </text>
    </svg>
  )
}

/** Tables — the six tables and why this tab exists. */
export function TablesDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 200"
      role="img"
      aria-labelledby="tb-t tb-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="tb-t">The six tables and how they connect</title>
      <desc id="tb-d">
        Matters is the universe of comparable deals. Each matter has many deal points, one per
        ABA question. Clauses come from a separate commercial-contract corpus and deliberately do
        not become matters. FOLIO concepts supply the industry vocabulary that matters and clauses
        reference. Labels record human review decisions. Ingest runs record what was loaded, when,
        and with what checksum.
      </desc>
      <Arrow id="tb-a" />

      <g className="loop__edges" markerEnd="url(#tb-a)">
        <path d="M232,50 H196" />
        <path d="M368,50 H404" />
        <path d="M300,72 V104" />
        <path d="M232,124 H196" />
      </g>

      <g className="loop__node loop__node--key">
        <rect x="232" y="30" width="136" height="40" rx="6" />
      </g>
      <g className="loop__node">
        <rect x="60" y="30" width="136" height="40" rx="6" />
        <rect x="404" y="30" width="136" height="40" rx="6" />
        <rect x="232" y="104" width="136" height="40" rx="6" />
        <rect x="60" y="104" width="136" height="40" rx="6" />
        <rect x="404" y="104" width="136" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="300" y="48">matters</text>
        <text x="128" y="48">deal_points</text>
        <text x="472" y="48">folio_concepts</text>
        <text x="300" y="122">clauses</text>
        <text x="128" y="122">labels</text>
        <text x="472" y="122">ingest_runs</text>
      </g>
      <g className="loop__sub">
        <text x="300" y="62">152 · the deal universe</text>
        <text x="128" y="62">12,937 · one per question</text>
        <text x="472" y="62">18,259 · the vocabulary</text>
        <text x="300" y="136">13,823 · matter_id NULL</text>
        <text x="128" y="136">your review decisions</text>
        <text x="472" y="136">what loaded, when, sha256</text>
      </g>

      <text className="loop__note" x="300" y="172">
        clauses carry no matter_id on purpose — 510 commercial contracts inside “comparable deals”
        would inflate every facet count
      </text>
      <text className="loop__note" x="300" y="186">
        this tab exists so nobody has to open psql to check a number the app just showed them
      </text>
    </svg>
  )
}

/** Admin — ingest, freshness, and what the operator is actually watching. */
export function AdminDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 200"
      role="img"
      aria-labelledby="ad-t ad-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="ad-t">Ingest, freshness, and what this tab watches</title>
      <desc id="ad-d">
        An ingest run writes rows and stamps each one with the time it changed. The semantic layer
        checks the maximum of those timestamps to decide whether its cached answers are stale; when
        the maximum moves, it recomputes. The measured delay between a write and a fresh aggregate
        is eleven point three seconds. This tab shows the last run per source with its checksum,
        the current extractor accuracy per deal point, and a live tail of structured logs.
      </desc>
      <Arrow id="ad-a" />

      <g className="loop__edges" markerEnd="url(#ad-a)">
        <path d="M130,44 H166" />
        <path d="M296,44 H332" />
        <path d="M462,44 H498" />
      </g>

      <g className="loop__node">
        <rect x="12" y="24" width="118" height="40" rx="6" />
        <rect x="166" y="24" width="130" height="40" rx="6" />
        <rect x="332" y="24" width="130" height="40" rx="6" />
        <rect x="498" y="24" width="90" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="71" y="42">ingest run</text>
        <text x="231" y="42">updated_at stamp</text>
        <text x="397" y="42">MAX(updated_at)</text>
        <text x="543" y="42">recompute</text>
      </g>
      <g className="loop__sub">
        <text x="71" y="56">rows change</text>
        <text x="231" y="56">per row, on write</text>
        <text x="397" y="56">the staleness check</text>
        <text x="543" y="56">11.3 s</text>
      </g>

      <text className="loop__note" x="300" y="92">WHAT THIS TAB SHOWS YOU, AND WHY EACH ONE MATTERS</text>

      <g className="loop__node">
        <rect x="12" y="104" width="182" height="46" rx="6" />
        <rect x="210" y="104" width="182" height="46" rx="6" />
        <rect x="408" y="104" width="180" height="46" rx="6" />
      </g>
      <g className="loop__label">
        <text x="103" y="122">last run per source</text>
        <text x="301" y="122">calibration table</text>
        <text x="498" y="122">live log tail</text>
      </g>
      <g className="loop__sub">
        <text x="103" y="136">rows, duration, sha256</text>
        <text x="301" y="136">accuracy per deal point</text>
        <text x="498" y="136">JSON lines, filterable</text>
        <text x="103" y="146">— did the data land?</text>
        <text x="301" y="146">— what may we claim?</text>
        <text x="498" y="146">— what is it doing now?</text>
      </g>

      <text className="loop__note" x="300" y="180">
        logs are JSON lines rather than prose so this tab can filter them without parsing English
      </text>
      <text className="loop__note" x="300" y="194">
        and secrets are stripped by a log processor, not by remembering to sanitise at each call
        site
      </text>
    </svg>
  )
}

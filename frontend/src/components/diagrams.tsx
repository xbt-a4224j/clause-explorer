/**
 * Per-tab explanatory diagrams (#35, reduced in #45).
 *
 * Inline SVG on design tokens so they cannot drift from the palette and stay legible at any
 * zoom. Every one is `role="img"` with a title AND a description that carries the same content
 * in words — a diagram that only works visually is not an explanation for everyone.
 *
 * There were five. #45 cut the explainer prose to what a tab is for plus its one honest limit,
 * and deleted the two diagrams whose argument no longer had prose beside it:
 * `ExploreDiagram` drew an industry hierarchy roll-up, and `AdminDiagram` drew the
 * `MAX(updated_at)` freshness chain. Both paragraphs moved to `docs/walkthrough.md`. The three
 * below survive because the claims they draw are still stated in the explainer beside them.
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

/** Tables — the five tables and why this tab exists. */
export function TablesDiagram() {
  return (
    <svg
      className="loop"
      viewBox="0 0 600 200"
      role="img"
      aria-labelledby="tb-t tb-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="tb-t">The five tables and how they connect</title>
      <desc id="tb-d">
        Matters is the universe of comparable deals. Each matter has many deal points, one per
        ABA question. Industries supply the vocabulary that matters reference.
        Labels record human review decisions. Ingest runs record what was loaded, when, and with
        what checksum.
      </desc>
      <Arrow id="tb-a" />

      <g className="loop__edges" markerEnd="url(#tb-a)">
        <path d="M232,50 H196" />
        <path d="M368,50 H404" />
      </g>

      <g className="loop__node loop__node--key">
        <rect x="232" y="30" width="136" height="40" rx="6" />
      </g>
      <g className="loop__node">
        <rect x="60" y="30" width="136" height="40" rx="6" />
        <rect x="404" y="30" width="136" height="40" rx="6" />
        <rect x="140" y="104" width="136" height="40" rx="6" />
        <rect x="324" y="104" width="136" height="40" rx="6" />
      </g>

      <g className="loop__label">
        <text x="300" y="48">matters</text>
        <text x="128" y="48">deal_points</text>
        <text x="472" y="48">industries</text>
        <text x="208" y="122">labels</text>
        <text x="392" y="122">ingest_runs</text>
      </g>
      <g className="loop__sub">
        <text x="300" y="62">152 · the deal universe</text>
        <text x="128" y="62">12,937 · one per question</text>
        <text x="472" y="62">20 · the vocabulary</text>
        <text x="208" y="136">your review decisions</text>
        <text x="392" y="136">what loaded, when, sha256</text>
      </g>

      <text className="loop__note" x="300" y="172">
        this tab exists so nobody has to open psql to check a number the app just showed them
      </text>
    </svg>
  )
}

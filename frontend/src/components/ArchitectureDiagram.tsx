/**
 * The whole system on one screen — engineering and product (#35).
 *
 * Lives on Admin because that is the operator's tab: the person asking "what is this thing
 * actually made of" is the same person watching ingest and reading logs.
 *
 * Two readings are deliberately overlaid. Left to right and top to bottom is the *engineering*
 * path — corpora, ingest, Postgres, the two query paths, the API, the tabs. The bottom band is
 * the *product* reading: which question each tab answers and for whom. They share the same
 * boxes on purpose, because a tab that cannot be traced to a question is a feature nobody
 * asked for.
 *
 * Gold versus inferred is marked throughout rather than legended once: mixing expert labels
 * with classifier output is the largest source of quiet error in this system.
 */
export function ArchitectureDiagram() {
  return (
    <svg
      className="arch"
      viewBox="0 0 1000 690"
      role="img"
      aria-labelledby="arch-t arch-d"
      preserveAspectRatio="xMinYMin meet"
    >
      <title id="arch-t">Clause Explorer architecture, engineering and product</title>
      <desc id="arch-d">
        Four public corpora feed an idempotent ingest into Postgres: MAUD supplies 152 merger
        agreements and 12,937 expert-labelled deal points; CUAD supplies 13,823 clauses; FOLIO
        supplies an 18,259-concept legal ontology used as the dimension vocabulary; SEC EDGAR
        supplies industry codes, which are inferred rather than labelled. Postgres holds six
        tables. Two independent query paths read from it: Cube Core defines 16 measures and 40
        dimensions in versioned YAML and computes every aggregate, while a hybrid retrieval
        index combines BM25 keyword scoring with 256-dimensional embeddings to rank comparable
        deals — ranking does not go through Cube. FastAPI serves both, and enforces the min_n
        refusal threshold server-side so no client or agent can bypass it. A language model may
        select from Cube's published catalog but never computes a number. Seven tabs sit on top,
        serving partners, knowledge management, and engineers.
      </desc>

      <defs>
        <marker
          id="ar"
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

      {/* ── 1 · SOURCES ─────────────────────────────────────────────── */}
      <text className="arch__band" x="20" y="20">
        1 · SOURCES — all public, all open licence
      </text>
      <g className="arch__gold">
        <rect x="20" y="28" width="176" height="52" rx="6" />
        <rect x="208" y="28" width="176" height="52" rx="6" />
        <rect x="396" y="28" width="176" height="52" rx="6" />
      </g>
      <g className="arch__inferred">
        <rect x="584" y="28" width="176" height="52" rx="6" />
      </g>
      <g className="arch__lbl">
        <text x="108" y="48">MAUD</text>
        <text x="296" y="48">CUAD</text>
        <text x="484" y="48">FOLIO</text>
        <text x="672" y="48">SEC EDGAR</text>
      </g>
      <g className="arch__sub">
        <text x="108" y="62">152 agreements</text>
        <text x="108" y="73">12,937 expert labels</text>
        <text x="296" y="62">510 contracts</text>
        <text x="296" y="73">13,823 clauses</text>
        <text x="484" y="62">18,259 concepts</text>
        <text x="484" y="73">the dimension vocabulary</text>
        <text x="672" y="62">SIC → FOLIO crosswalk</text>
        <text x="672" y="73">134 of 152 · INFERRED</text>
      </g>

      {/* legend */}
      <g className="arch__gold">
        <rect x="790" y="28" width="14" height="14" rx="3" />
      </g>
      <g className="arch__inferred">
        <rect x="790" y="50" width="14" height="14" rx="3" />
      </g>
      <text className="arch__legend" x="812" y="39">
        expert-labelled (gold)
      </text>
      <text className="arch__legend" x="812" y="61">
        inferred — classifier output
      </text>
      <text className="arch__legend" x="790" y="80">
        dashed = the model may not reach it
      </text>

      {/* ── 2 · INGEST ─────────────────────────────────────────────── */}
      <text className="arch__band" x="20" y="110">
        2 · INGEST — idempotent, provenance recorded
      </text>
      <g className="arch__box">
        <rect x="20" y="118" width="740" height="44" rx="6" />
      </g>
      <text className="arch__lbl" x="390" y="136">
        folio → maud → edgar → cuad
      </text>
      <text className="arch__sub" x="390" y="151">
        sha256 per file · IS DISTINCT FROM guard so a no-op re-run does not invalidate Cube ·
        every row keeps source_file + char offsets
      </text>
      <g className="arch__edge" markerEnd="url(#ar)">
        <path d="M108,80 V118" />
        <path d="M296,80 V118" />
        <path d="M484,80 V118" />
        <path d="M672,80 V118" />
        <path d="M390,162 V186" />
      </g>

      {/* ── 3 · POSTGRES ───────────────────────────────────────────── */}
      <text className="arch__band" x="20" y="180">
        3 · STORE — Postgres 16
      </text>
      <g className="arch__store">
        <rect x="20" y="186" width="740" height="76" rx="6" />
      </g>
      <g className="arch__inner">
        <rect x="32" y="198" width="116" height="30" rx="4" />
        <rect x="156" y="198" width="116" height="30" rx="4" />
        <rect x="280" y="198" width="116" height="30" rx="4" />
        <rect x="404" y="198" width="116" height="30" rx="4" />
        <rect x="528" y="198" width="106" height="30" rx="4" />
        <rect x="642" y="198" width="106" height="30" rx="4" />
      </g>
      <g className="arch__tbl">
        <text x="90" y="217">matters</text>
        <text x="214" y="217">deal_points</text>
        <text x="338" y="217">clauses</text>
        <text x="462" y="217">folio_concepts</text>
        <text x="581" y="217">labels</text>
        <text x="695" y="217">ingest_runs</text>
      </g>
      <g className="arch__sub">
        <text x="90" y="240">152</text>
        <text x="214" y="240">12,937 · LONG</text>
        <text x="338" y="240">13,823</text>
        <text x="462" y="240">18,259</text>
        <text x="581" y="240">human review</text>
        <text x="695" y="240">run history</text>
      </g>
      <text className="arch__note" x="390" y="256">
        updated_at trigger uses clock_timestamp(), not now() — transaction-start time would never
        advance and Cube would serve stale aggregates silently
      </text>

      {/* ── 4 · TWO QUERY PATHS ────────────────────────────────────── */}
      <text className="arch__band" x="20" y="286">
        4 · TWO INDEPENDENT QUERY PATHS
      </text>
      <g className="arch__box2">
        <rect x="20" y="294" width="356" height="80" rx="6" />
        <rect x="404" y="294" width="356" height="80" rx="6" />
      </g>
      <g className="arch__lbl">
        <text x="198" y="314">Cube Core — the semantic layer</text>
        <text x="582" y="314">Hybrid retrieval — NOT via Cube</text>
      </g>
      <g className="arch__sub">
        <text x="198" y="330">16 measures · 40 dimensions in versioned YAML</text>
        <text x="198" y="343">medians are percentile_cont, never avg</text>
        <text x="198" y="356">refresh_key = MAX(updated_at) · 11.3 s window</text>
        <text x="198" y="369">every aggregate in the product</text>
        <text x="582" y="330">BM25 keyword + 256-dim float16 embeddings</text>
        <text x="582" y="343">α = 0.5 · MRR 0.785 vs 0.744 pure vector</text>
        <text x="582" y="356">cache committed, 9.5 MB — works with no API key</text>
        <text x="582" y="369">ranking is not an aggregate, so it skips the layer</text>
      </g>
      <g className="arch__edge" markerEnd="url(#ar)">
        <path d="M198,262 V294" />
        <path d="M582,262 V294" />
        <path d="M198,374 V404" />
        <path d="M582,374 V404" />
      </g>

      {/* ── 5 · API + THE GATE ─────────────────────────────────────── */}
      <text className="arch__band" x="20" y="398">
        5 · SERVE — FastAPI, 23 routes
      </text>
      <g className="arch__box">
        <rect x="20" y="404" width="740" height="68" rx="6" />
      </g>
      <g className="arch__gate">
        <rect x="36" y="416" width="200" height="44" rx="5" />
      </g>
      <text className="arch__lbl" x="136" y="434">
        min_n = 5 · REFUSAL GATE
      </text>
      <g className="arch__sub">
        <text x="136" y="449">server-side · a raw curl is refused too</text>
        <text x="500" y="430">structured JSON logs, secrets stripped by a processor</text>
        <text x="500" y="444">every figure leaves with its denominator attached</text>
        <text x="500" y="458">count below 30, percentage above — decided per row</text>
      </g>

      {/* the agent path, annotated separately */}
      <g className="arch__agent">
        <rect x="790" y="294" width="196" height="178" rx="6" />
      </g>
      <text className="arch__lbl" x="888" y="314">
        The agent path
      </text>
      <g className="arch__sub">
        <text x="888" y="332">reads Cube&rsquo;s /meta</text>
        <text x="888" y="345">label space = 56 names</text>
        <text x="888" y="365">emits a SELECTION,</text>
        <text x="888" y="378">never SQL, never a number</text>
        <text x="888" y="398">filter values resolved</text>
        <text x="888" y="411">against real data, or</text>
        <text x="888" y="424">fail loudly — never empty</text>
        <text x="888" y="444">graded offline: 11 of 20</text>
        <text x="888" y="457">refusal: 1 of 5 ← the gap</text>
      </g>
      <g className="arch__edge" markerEnd="url(#ar)">
        {/* routed UNDER the retrieval box, not through it: the direct line from the agent panel
            to Cube crossed "BM25 keyword + 256-dim float16 embeddings" and struck out the text */}
        <path d="M790,386 H170 V378" />
        <path d="M888,472 V492 H760" />
      </g>

      {/* ── 6 · PRODUCT ────────────────────────────────────────────── */}
      <text className="arch__band" x="20" y="496">
        6 · PRODUCT — seven tabs, three audiences, one set of governed numbers
      </text>
      <g className="arch__edge" markerEnd="url(#ar)">
        <path d="M390,472 V504" />
      </g>

      <g className="arch__box2">
        <rect x="20" y="512" width="300" height="58" rx="6" />
        <rect x="348" y="512" width="300" height="58" rx="6" />
        <rect x="676" y="512" width="304" height="58" rx="6" />
      </g>
      <g className="arch__lbl">
        <text x="170" y="530">PARTNER</text>
        <text x="498" y="530">KNOWLEDGE MANAGEMENT</text>
        <text x="828" y="530">ENGINEER</text>
      </g>
      <g className="arch__sub">
        <text x="170" y="546">Explore · Deal Terms</text>
        <text x="498" y="546">Coverage · Label</text>
        <text x="828" y="546">Semantic Layer · Tables · Admin</text>
        <text x="170" y="562">“what looks like my deal, and what was negotiated?”</text>
        <text x="498" y="562">“where are we thin, and what should we fix first?”</text>
        <text x="828" y="562">“prove the number, and show me the definition”</text>
      </g>

      {/* ── 7 · THE THREE RULES ────────────────────────────────────── */}
      <text className="arch__band" x="20" y="596">
        7 · THE RULES THAT SHAPE ALL OF THE ABOVE
      </text>
      <g className="arch__rule">
        <rect x="20" y="604" width="313" height="66" rx="6" />
        <rect x="343" y="604" width="314" height="66" rx="6" />
        <rect x="667" y="604" width="313" height="66" rx="6" />
      </g>
      <g className="arch__lbl">
        <text x="176" y="622">Every figure carries its n</text>
        <text x="500" y="622">Refuse rather than guess</text>
        <text x="823" y="622">Gold and inferred never mix</text>
      </g>
      <g className="arch__sub">
        <text x="176" y="638">“6 of 8”, not “75%” — a percentage over</text>
        <text x="176" y="650">eight deals implies precision the sample</text>
        <text x="176" y="662">cannot support</text>
        <text x="500" y="638">min_n does three jobs: statistical honesty,</text>
        <text x="500" y="650">extraction confidence, and k-anonymity —</text>
        <text x="500" y="662">n=1 is one client&rsquo;s negotiated term</text>
        <text x="823" y="638">is_inferred_* lives in the schema, not the</text>
        <text x="823" y="650">docs. 495 of 12,937 spans are NULL rather</text>
        <text x="823" y="662">than a guess that opens the wrong clause</text>
      </g>
    </svg>
  )
}

import { Term } from './Term'

/**
 * The standing per-tab explanation (#35).
 *
 * Each answers the same three questions in the same order, because a reader who learns the
 * shape on one tab can skim it on the next:
 *
 *   1. What this tab is for — the job, in the user's terms, not the feature's
 *   2. What you can do here — the actual gestures, including keyboard
 *   3. Why this beats the obvious alternative — stated honestly, including where it fails
 *
 * Jargon is expanded on first use, on every tab. Someone who lands on Coverage first should not
 * have to visit Explore to learn what MAUD is. The repetition is deliberate.
 */

export function ExploreExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Answering &ldquo;what have we got that looks like
        the deal in front of me?&rdquo; A partner pitching for new work needs comparable deals —
        same industry, same rough era — and needs them before tomorrow. Today that question takes
        a knowledge-management professional days across three systems and comes back incomplete.
      </p>
      <p>
        <strong>What you are searching.</strong> 152 real merger agreements from{' '}
        <strong><Term>MAUD</Term></strong> — the <em>Merger Agreement Understanding Dataset</em>, public
        filings that lawyers annotated for research use. These are <em>public SEC filings, not
        any firm&rsquo;s own matter history</em>. Industry comes from <strong><Term>FOLIO</Term></strong>, an
        open ontology of legal concepts. It supplies the stable <em>codes</em> filtering joins on,
        and the labels you see. Its hierarchy is loaded and the query walks it — but on this
        corpus every matter sits at the same level, so the walk currently returns exactly what
        an equality match would. The pharma-and-devices grouping happens in a checked-in SIC
        crosswalk, not in the ontology.
      </p>
      <p>
        <strong>What you can do here.</strong> Type a description of your deal, or press{' '}
        <code>/</code> to jump to the search box. Narrow with the facet rail on the left; the
        counts recompute against whatever is left, so they always describe the set you are
        actually looking at. Values with nothing behind them stay visible but disabled — what the
        corpus <em>lacks</em> is information too. <code>j</code> and <code>k</code> move through
        results, <code>Enter</code> opens one. Every card carries its source file, and every
        industry says whether it was inferred.
      </p>
      <p>
        <strong>Why an ontology instead of a keyword search.</strong> Because filtering joins on a
        concept <em>code</em>, not a display label. A label can drift — &ldquo;Health Care
        Industry&rdquo; versus &ldquo;Healthcare&rdquo; — and a near-miss returns zero results,
        which reads identically to <em>&ldquo;we have no comparable deals&rdquo;</em>. That is the
        most dangerous failure this product can have, because it is a wrong answer that looks like
        a finding. A code cannot drift.
      </p>
      <p>
        <strong>Where this is thin, stated up front.</strong> The corpus spans 20 months
        (March 2020 – November 2021), not five years. Deal value is empty for all 152 agreements —
        the SEC endpoints do not carry transaction value — so size filtering does not work yet, and
        the rail says so rather than offering a filter that cannot narrow anything. And every
        industry is <em><Term>inferred</Term></em> from a coarse, self-assigned SEC code through a hand-written
        crosswalk; 134 of 152 resolved, and a hand check of 20 found 3 carrying the acquirer&rsquo;s
        industry rather than the target&rsquo;s.
      </p>
    </>
  )
}

export function DealTermsExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Replacing the afternoon an associate spends reading
        eight merger agreements side by side to answer &ldquo;what did we actually negotiate across
        these?&rdquo;
      </p>
      <p>
        <strong>What a &ldquo;deal point&rdquo; is.</strong> One negotiated provision, written as a
        question with a fixed answer set. The American Bar Association maintains 92 of them for
        public-target deals — <em><Term>public target</Term></em> meaning the company being acquired is publicly
        traded, which is why these agreements are public records at all. Examples: does the target&rsquo;s
        board keep a <em><Term>fiduciary out</Term></em>, letting it change its recommendation if a better offer
        arrives? Is there a <em><Term>reverse termination fee</Term></em> — what the buyer pays to walk away? Is
        knowledge <em>Actual</em> or <em>Constructive</em>?
      </p>
      <p>
        <strong>Why anyone cares.</strong> Every two years the ABA publishes its Public Target Deal
        Points Study: a committee reads a sample by hand and reports how often each provision
        appears. Lawyers cite it to argue what is <em>market</em> — &ldquo;a 3.5% reverse
        termination fee is above market at this size.&rdquo; It is the reference work, it is built
        by hand, and nobody made it queryable. This is the same comparison scoped to the deals in
        front of you.
      </p>
      <p>
        <strong>What you can do here.</strong> Pick a set in Explore; the selection carries over.
        Each row is one deal point with its prevalence across that set. Click any row to see the
        actual clause language from the agreements that have it, with the file and character
        offsets it was read from.
      </p>
      <p>
        <strong>Why counts and not percentages.</strong> Below a sample of 30 a row renders
        &ldquo;6 of 8&rdquo;, never &ldquo;75%&rdquo;. A percentage implies a precision eight deals
        cannot support, and reporting one as though it were market is the specific failure this
        domain punishes. The switch is decided per row on how many of your deals answer{' '}
        <em>that</em> question — not on the size of the selection, because those are different
        numbers.
      </p>
      <p>
        <strong>Two more rules worth knowing.</strong> A deal point that <em>no</em> deal in your
        set has still appears, as &ldquo;0 of 8&rdquo; — absence is a finding, and a missing row
        would read as &ldquo;nobody asked&rdquo;. And medians are true percentiles, never averages:
        on this corpus the mean and median reverse termination fee diverge substantially, and the
        mean is the number that looks right and is wrong.
      </p>
    </>
  )
}

export function CoverageExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Knowing where experience is thick and where it is
        thin, before you promise a client something. Built for knowledge-management — the function
        inside a firm responsible for making the firm&rsquo;s own experience findable — and for
        anyone triaging whether a pitch is worth chasing.
      </p>
      <p>
        <strong>How to read the grid.</strong> Every deal is placed in a cell by industry and
        period. Each cell shows how many deals sit in it. <strong>Thin and empty cells are styled
        loudly rather than faded</strong>, which is the opposite of the usual instinct — a gap is
        more actionable than a strength you already knew about. On the current corpus 33 of 45
        cells are too thin to characterize and only 12 are reportable.
      </p>
      <p>
        <strong>What happens when you click a thin cell.</strong> It takes you to Explore,
        pre-filtered, and then Deal Terms <em>refuses</em>: <code>n=3 — insufficient to
        characterize (threshold 5)</code>. That refusal has its own visual state, deliberately
        distinct from &ldquo;no results&rdquo;, because &ldquo;we will not answer this&rdquo; and
        &ldquo;there is nothing here&rdquo; are different statements.
      </p>
      <p>
        <strong>Why refusing is a feature.</strong> One threshold does three jobs at once.{' '}
        <em>Statistical honesty</em> — a median over three deals is not market.{' '}
        <em>Extraction confidence</em> — where accuracy has been measured, 4 of the 5 deal points
        tested fall below the reporting gate, and a thin slice is exactly where that bites. And{' '}
        <em><Term>k-anonymity</Term></em>: an analyst who can filter until one deal remains has extracted a
        single client&rsquo;s negotiated term through the analytics layer without ever opening a
        document. In a firm that is a confidentiality control, not a nicety.
      </p>
      <p>
        <strong>The gate is server-side.</strong> Not a hidden button — the API refuses too. You
        can try it with a raw <code>curl</code> and get the same refusal, and there is a test whose
        entire job is to prove that.
      </p>
      <p>
        <strong>One judgement call you should know about.</strong> &ldquo;Health Care&rdquo; here
        groups pharma, biotech, devices and contract research organisations, which the standard
        industry classification does not. That grouping is <em>our</em> definition: it produces 25
        matters where the standard one produces 3. A partner asking for healthcare comparables
        means the 25 — but it is a departure, and the UI says so wherever it appears.
      </p>
    </>
  )
}

export function TablesExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Checking the app&rsquo;s homework without a
        database client. Every figure this product shows is an aggregate over rows, and those rows
        are right here, sortable and filterable. Nobody should have to open <code>psql</code> to
        verify a number the app just put on screen.
      </p>
      <p>
        <strong>What the five tables are.</strong> <code>matters</code> is the universe of
        comparable deals — 152 merger agreements. <code>deal_points</code> holds one row per
        agreement per ABA question, 12,937 of them. <code>folio_concepts</code> is the
        18,259-concept legal ontology supplying the industry vocabulary. <code>labels</code>
        records human review decisions. <code>ingest_runs</code> records what was loaded, when,
        how long it took and with what checksum.
      </p>
      <p>
        <strong>What to look for.</strong> Sorting and filtering happen on the server, and the
        state is mirrored into the URL, so a row you found is a link you can send. Every table
        marks which of its columns are <em>inferred</em> rather than expert-labelled — that
        distinction is the largest source of quiet error in a system like this, so it is in the
        schema rather than only in documentation.
      </p>
      <p>
        <strong>The provenance rule this tab lets you test.</strong> A row whose text cannot be
        traced to a byte range in a downloaded file is a bug. Deal-point rows carry their source
        file and character offsets; open the file at those offsets and you get exactly that text, never
        a paraphrase. 3.8% of deal points have no located span at all, and they store NULL rather
        than a nearest guess — a wrong offset opens the wrong clause and looks completely right.
      </p>
    </>
  )
}

export function AdminExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Answering three operator questions without reading
        a log file by hand: did the data land, what are we currently allowed to claim, and what is
        the system doing right now.
      </p>
      <p>
        <strong>Ingest status.</strong> One row per load, per source, with rows read, rows
        upserted, duration and a SHA-256 of the file it read. Loads are idempotent, so re-running
        is safe — and unchanged rows are deliberately not rewritten, because the semantic layer
        decides whether its cached answers are stale by looking at the newest change timestamp. An
        unconditional rewrite would make a no-op reload invalidate every cached figure in the
        product.
      </p>
      <p>
        <strong>Calibration — the most important table here.</strong> <Term>MAUD</Term>&rsquo;s answers were
        written by lawyers, so they are ground truth, not model output. That makes it possible to
        run an extractor over agreements deliberately held back, compare its answers to the human
        ones, and publish accuracy <em>per deal point</em> with a confidence interval. That is what
        makes &ldquo;this works on documents nobody annotated&rdquo; a testable claim instead of a
        sales line.
      </p>
      <p>
        <strong>Read it expecting bad news.</strong> Of the 5 deal points measured so far, 4 fall
        below the 0.7 reporting gate — accuracies of 0.50, 0.30, 0.30 and 0.20 against one of 0.95.
        That is the table doing its job: it tells you precisely which questions the system must
        decline to answer on un-annotated documents. A calibration where everything passes is
        usually a calibration that was not run honestly.
      </p>
      <p>
        <strong>Freshness.</strong> Writes stamp each changed row; the semantic layer polls the
        maximum of those stamps and recomputes when it moves. Measured delay between a write and a
        fresh aggregate: <strong>11.3 seconds</strong>. Worth knowing before you re-ingest and
        wonder why a number has not moved.
      </p>
      <p>
        <strong>Logs.</strong> Structured JSON lines rather than prose, which is why this tab can
        filter them without parsing English. Every request carries an id that follows it down the
        call stack. Secrets are stripped by a processor in the logging pipeline rather than by
        remembering to sanitise at each call site — a credential must not be able to reach the log
        because one caller forgot.
      </p>
    </>
  )
}

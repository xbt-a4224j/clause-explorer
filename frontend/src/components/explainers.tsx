import { Term } from './Term'

/**
 * The standing per-tab explanation (#35, cut to size in #45).
 *
 * Each body is two paragraphs and about a hundred words: **what the tab is for**, and **the
 * one honest limit**. It was five or six paragraphs per tab — roughly 2,900 words of essay
 * across the app, more than the README — which put a document in front of the instrument on
 * every tab. The argument that was cut is not gone: it moved to `docs/walkthrough.md`, under
 * "Why it is built this way", where a reader who wants it can read all of it at once.
 *
 * Jargon still expands on first use through `<Term>`, on every tab, because someone who lands
 * on Ask first should not have to visit Explore to learn what MAUD is. The definitions
 * live in the glossary rather than in prose, which is most of what made the cut affordable.
 *
 * Every number below traces to a command in `docs/walkthrough.md` or `docs/results/`.
 */

export function ExploreExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Finding deals that look like the one in front of
        you. Faceted search over 152 real merger agreements from <strong><Term>MAUD</Term></strong>{' '}
        — public SEC filings, not any firm&rsquo;s own matter history. Type a description or press{' '}
        <code>/</code> for the search box, narrow with the rail, and the counts recompute against
        whatever is left. Industry filtering joins on a <strong><Term>FOLIO</Term></strong> concept
        code rather than a display label, so a near-miss cannot return zero rows that read as
        &ldquo;no comparable deals&rdquo;.
      </p>
      <p>
        <strong>The limit.</strong> The corpus spans 20 months (March 2020 – November 2021), not
        five years, and deal value is empty for all 152 agreements, so size filtering does not
        work yet. Every industry is <em><Term>inferred</Term></em> from a coarse SEC code: 134 of
        152 resolved, and a hand check of 20 found 3 carrying the acquirer&rsquo;s industry rather
        than the target&rsquo;s.
      </p>
    </>
  )
}

export function DealTermsExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Answering &ldquo;what did we negotiate across
        these?&rdquo; without reading eight agreements side by side. Each row is one{' '}
        <Term>deal point</Term> — a provision written as a question with a fixed answer set, the
        way the ABA&rsquo;s Public Target Deal Points Study asks it — with its prevalence across
        the set you picked in Explore. Click a row for the clause language, with the file and
        character offsets it was read from.
      </p>
      <p>
        <strong>The limit.</strong> It answers only the ABA&rsquo;s 92 questions; a provision
        outside that set is invisible here, not absent from the agreements. Below a sample of 30 a
        row renders &ldquo;6 of 8&rdquo;, never &ldquo;75%&rdquo; — a percentage claims precision
        eight deals cannot support.
      </p>
    </>
  )
}

export function AdminExplainer() {
  return (
    <>
      <p>
        <strong>What this tab is for.</strong> Three operator questions without reading a log file
        by hand: did the data land, what are we currently allowed to claim, and what is the system
        doing right now. Ingest rows carry rows upserted, duration and a SHA-256 of the file read.
        Calibration grades our extractor against <Term>MAUD</Term>&rsquo;s lawyer-written answers,
        per deal point. The log viewer tails structured JSON lines, each carrying a request id.
      </p>
      <p>
        <strong>The limit, which is the calibration table.</strong> Of the 5 deal points measured,
        4 fall below the 0.7 reporting gate — accuracies of 0.50, 0.30, 0.30 and 0.20 against one
        of 0.95. That is the table doing its job: it names which questions the system must decline
        to answer on un-annotated documents.
      </p>
    </>
  )
}

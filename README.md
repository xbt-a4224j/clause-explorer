# Clause Explorer

A comparable-deals workbench for transactional contract work. Find deals like the one in front of
you, see what was negotiated across them, and know where your experience is thin.

![Overview — three journeys, each with the path it takes through the app](docs/img/overview.png)

*The landing tab. Three questions, the person who asks each one, what it costs them today, and the
clicks that answer it. **Run this** lands on the first step already filtered. The tab bar splits
after Coverage: four tabs are the product, four are the evidence that its answers are trustworthy.*

## Three journeys

**1 · The comparables request.** *A knowledge-management analyst: "Partner is pitching a healthcare
target tomorrow, all cash. What did boards get on fiduciary outs?"* Today: search the document
system by keyword, open eight agreements, read each no-shop section, build a table by hand.

![Explore — faceted comparable-deal search over 152 real merger agreements](docs/img/explore.png)

*Explore. A plain-English description plus one facet narrows 152 agreements to 25, ranked by hybrid
retrieval. Add the All Cash facet and it is 21. Note the header: **134 filterable**, not 152 — eighteen matters have no industry at all,
and the count says what the dimension can actually narrow. Every row is badged **INFERRED**, because
industry is derived from the SEC's coarse self-assigned code rather than a lawyer's label.*

![Deal Terms — the rollup, in counts rather than percentages](docs/img/deal-terms.png)

*Deal Terms. The comparison an associate builds by hand from a stack of agreements: 90 deal points
answered across n=21, two answered by none of them. Nothing renders as a percentage below n=30,
because a percentage implies a precision the sample cannot support. Each row carries its full
answer distribution, since "21 of 21 present" would hide the disagreement that matters — on this
slice, specific performance is "entitled to" in 20 and "entitled to seek" in one.*

![The drill-through, naming a document-scale span for what it is](docs/img/deal-terms-drill.png)

*The drill-through, and the honest half of it. MAUD records where in the agreement an answer was
found, which for holistic deal points is most of the document — the span here is 238,751 characters.
Presenting that under the word "clause" showed a table of contents, so a span wider than
`max_clause_chars` is labelled a document-scale span and shown as a bounded excerpt.*

**2 · Is that actually market?** *An associate: "A partner said everyone is doing commercially
reasonable efforts now. Is that true?"* On the healthcare all-cash slice it is not: flat covenant 10,
commercially reasonable 8, reasonable best 3, across n=21. Narrow it further and the gate takes
over.

![Semantic Layer — the query builder refusing a slice of one](docs/img/refusal.png)

*Semantic Layer. The agent selects from named measures and dimensions and nothing else — there is no
free-text box in the builder, which is the point. Here a query has been narrowed to a single company,
and the server **refuses**: `n=1, threshold 5`. That gate is server-side, so a raw `curl` gets the
same answer.*

![Coverage — thin cells styled prominently](docs/img/coverage.png)

*Coverage. Where the corpus is thick or thin. The sparse cells are the prominent ones, because a gap
is a finding about the corpus rather than something to smooth over.*

**3 · Where can the extractor be trusted?** *A data manager: "Before this runs over our own
precedents, where is it weak?"* Admin publishes accuracy per deal point on held-out gold; Label
queues the disagreements. This journey is **half built**, and the tab says so on screen.

![Label — the review queue, ranked by extractor disagreement](docs/img/label.png)

*Label. Two extractors read the same contract: a language model and a keyword baseline. Where they
disagree, at least one is wrong, which is the cheapest useful ranking signal available before any
calibrated confidence score exists. Decisions are recorded; calibration does not read them back yet.*

## The problem

A partner pitching a healthcare private-equity sponsor needs, by tomorrow: *our comparable deals —
healthcare, sponsor-side, $200M–1B, last five years — with what was negotiated in each, and a
paragraph for the pitch deck.*

Today that takes a knowledge-management professional days, across three systems, and the answer
comes back incomplete. It's one of the most-complained-about problems in law firm KM, and it's the
reason legal-matter taxonomies exist at all — you cannot answer "healthcare PE deals" unless matters
are described consistently.

## What it does

The four tabs an analyst uses:

| | |
|---|---|
| **Explore** | Faceted comparable-deal search. Filter by industry, signing year and consideration type — facet counts recompute live against whatever is left. Ranked by hybrid retrieval. |
| **Deal Terms** | Rollup across the selected set, with the full answer distribution per row, drilling through to the source text at a character range in the filing. |
| **Coverage** | Where experience is thick or thin. Thin cells are the signal — a gap is more actionable than a strength you already know about. |
| **Overview** | The three journeys above, each runnable from the card. |

And the four behind the divider, which are the evidence rather than the product:

| | |
|---|---|
| **Semantic Layer** | The vocabulary the agent may select from, read live from Cube, with a query builder that has no free-text box and an offline grade of the selections. |
| **Tables / Admin** | Browsable raw data, ingest status, the calibration table, an architecture diagram, and live structured logs. |
| **Label** | A review queue ranked by disagreement between two extractors. Honest caveat: nothing reads its output yet — see Limitations. |

## Why it refuses to answer sometimes

Slice a few hundred deals by industry × size × term and cells get thin fast. Reporting a median over
three deals as "market" is the failure this domain punishes, so below a configurable `min_n` the
answer is `n=3 — insufficient to characterize`, not a confident number. Every figure carries its
denominator; counts render as "6 of 8" rather than "75%" when the sample can't support a percentage.

That threshold does three jobs at once: statistical honesty, extraction-confidence gating, and
**k-anonymity** — because an analyst who can filter until n=1 has extracted a single client's
negotiated term through the aggregate layer without ever retrieving a document.

## Why a semantic layer

An agent answering analytical questions has two independent ways to be wrong: the number, and the
*definition* of the number. Text-to-SQL leaves both open and is hard to grade — you end up diffing
freeform queries.

Putting [Cube Core](https://cube.dev) (Apache-2.0) between the agent and the warehouse means metrics
are defined once in versioned YAML, and the agent selects from *named measures* over a metadata
endpoint. The number is computed by Postgres, never generated by the model. Correctness becomes
discrete — did it pick the right measure and filters? — which is gradeable offline, with no database
and no LLM in the loop.

The risk doesn't vanish, it relocates: a wrong *selection* returns a real number for the wrong
question. So the resolved query is shown above every answer — `median RTF · healthcare · $200M–1B ·
n=8` — putting a misinterpretation in front of the one person qualified to catch it.

## Data

| Source | What | License |
|---|---|---|
| [MAUD](https://www.atticusprojectai.org/maud/) | 152 real merger agreements, 47k+ expert annotations across the 92 ABA Public Target Deal Points | CC BY 4.0 |
| [CUAD](https://www.atticusprojectai.org/cuad) | commercial contracts, 41 expert-annotated clause types | CC BY 4.0 |
| [FOLIO](https://github.com/alea-institute/FOLIO) | 18,000+ legal concepts in OWL — the dimension vocabulary | CC BY |
| SEC EDGAR | industry (SIC), deal value, dates, parties for the same agreements | public |

MAUD's expert annotations are the product data — we don't re-extract what lawyers already labeled.
Extraction is a separate **calibration experiment**: run the extractor over a held-out MAUD slice,
compare against the labels, publish the accuracy per deal point. That's what makes the claim
"usable on documents nobody annotated" testable rather than asserted.

## Limitations

Every figure below comes from a command that ran. What the product does not do, stated here
rather than discovered later.

- **Industry is inferred, on every matter.** A checked-in SIC to FOLIO crosswalk over the SEC's
  self-assigned code resolves 134 of 152. A 20-matter hand check found the registrant was the
  target in 17 and the acquirer in 3. The grouping is ours: it puts pharma, biotech, devices and
  CROs under Health Care (25 matters); straight NAICS would leave Health Care at 3.
- **Deal value is empty** for all 152 matters. EDGAR's company endpoints do not carry
  transaction value, so there is no size filter (#9). Consideration type, a MAUD expert label, is
  the third facet instead.
- **The corpus is 20 months**, 2020-03-13 to 2021-11-21.
- **Most recorded spans are not clauses.** Over the 12,442 deal points with a span, the median
  width is 4,658 characters and the 90th percentile is 238,949. MAUD marks where an answer was
  found, and for a holistic deal point that is most of the agreement. Spans wider than 6,000
  characters render as a labelled excerpt, not as the clause. A further 495 deal points (3.8%)
  have no span at all and store NULL rather than a nearest guess.
- **FOLIO's hierarchy is inert here.** Every matter sits at one level, so the descendant walk
  returns what an equality match would. What FOLIO earns is a stable code to join on.
- **CUAD is loaded and unused.** 13,823 clauses with provenance, attached to no matter, visible
  only in Tables. Mixing 510 commercial contracts into "comparable deals" would inflate every
  facet count. No CUAD row has an industry.
- **The Label loop does not close.** Decisions write to `labels`; calibration does not read them.
  On this corpus it could not usefully: every queued item already has a lawyer's answer.
- **The extractor is mostly below its own gate.** Of 5 calibrated deal points, 4 are under 0.7
  accuracy (0.50, 0.30, 0.30, 0.20; one at 0.95). Published so it is clear which questions the
  system must decline on un-annotated documents.

## Stack

Python 3.12 · FastAPI · Postgres 16 · Cube Core · React + TypeScript + Vite · rdflib · rank-bm25 ·
structlog. All open source. Retrieval, facets, coverage, and every table view work **without an API
key**; the key is needed only for generation and fresh embeddings.

## Walkthrough

Worked examples with real observed output from the running stack:
[`docs/walkthrough.md`](docs/walkthrough.md). The three journeys above, narrated end to end with
every figure verified against a live instance: [`docs/demo-scripts.md`](docs/demo-scripts.md).

The annotated screenshots in this README are generated, not captured by hand:
`cd frontend && node scripts/shots.mjs` re-shoots the whole set against a running app, locating
each callout by CSS selector, so they cannot silently drift from the UI.

## Quickstart

```bash
cp .env.example .env      # OPENAI_API_KEY optional — most of the app runs without it
docker compose up --build
make ingest               # FOLIO -> MAUD -> EDGAR enrich -> CUAD, idempotent
```

- App → http://localhost:5173
- API docs → http://localhost:8000/docs
- Cube playground → http://localhost:4000

## Development

```bash
make test     # everything that runs with no API key
make check    # ruff, mypy, tsc, tests — what CI enforces
make eval     # eval + calibration harnesses; writes docs/results/
make logs     # tail structured logs
```

## License

Code MIT. Corpora are CC BY (MAUD, CUAD, FOLIO) — attribution and provenance, including download
commands and checksums, in `docs/provenance.md`.

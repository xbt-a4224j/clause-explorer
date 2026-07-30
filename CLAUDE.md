# Clause Explorer — context for AI coding assistants

Read this before touching anything. Architecture, constraints, and the things that are easy
to get wrong.

## What this is

A **comparable-deals workbench** for transactional attorneys and knowledge-management teams.

The user story it exists for: *a partner is pitching a healthcare private-equity sponsor and needs,
by tomorrow, our comparable deals — healthcare, sponsor-side, $200M–1B, last five years — with what
was negotiated in each and a paragraph they can paste into the pitch.* Today that takes a KM
professional days across three systems and comes back incomplete.

Three questions the product answers:

1. **Find comparables** — which deals look like the one in front of me?
2. **What was negotiated across them** — fiduciary out in 6 of 8, ticking fee in 2
3. **Where are we thick or thin** — coverage by practice area, for pitch triage and KM curation

## Thesis

The ABA produces its Public Target Deal Points Studies by hand, annually, by committee — because
knowing what's market genuinely matters and nobody made it queryable. This makes it queryable, with
the discipline the manual version has and most AI tools drop: every figure carries its sample size,
drills through to the clauses behind it, and the system refuses to characterize a slice too thin to
support a claim.

Engineering claim: an agent answering analytical questions over legal data has two independent ways
to be wrong — the number, and the *definition* of the number. Constraining it to select from a
versioned named-measure vocabulary instead of generating SQL closes the second and makes the first
measurable offline.

## Architecture

```
MAUD (152 merger agreements · 47k expert labels · 92 ABA deal points · CC BY 4.0)
CUAD (commercial contracts · 41 clause types)     FOLIO (18k legal concepts, OWL)
EDGAR (SIC industry · deal value · dates · parties, for the same 152)
   │
   ▼  idempotent ingest, provenance recorded
Postgres ──► Cube Core (measures + FOLIO dimensions, defined once in YAML)
   │              │
   │         ┌────┴────┐
   │         ▼         ▼
   │    Dashboard   Agent (reads /meta, emits a selection — never SQL)
   │         └── same governed numbers ──┘
   ▼
Hybrid retrieval (BM25 + vector) ── comparable-deal ranking; NOT via Cube
```

**Cube's footprint is bounded.** It powers facet counts, the deal-terms rollup over a selected set,
and the coverage grid. It does **not** do retrieval, ranking, individual record fetch, or generation.

## The tabs

| Tab | For | What |
|---|---|---|
| **Explore** | partner | faceted comparable-deal search, live facet counts, matter cards |
| **Deal Terms** | partner | rollup over the selected set — "6 of 8", drill-through to clause text |
| **Coverage** | KM | FOLIO × deal-size grid; **thin cells are the signal, style them prominently** |
| **Tables** | you | browsable raw tables, sort/filter/paginate — so nobody opens psql |
| **Admin** | you | ingest status, calibration table, eval results, **live log viewer** |
| **Label** | KM | keyboard-driven labeling that feeds the review queue and re-calibration |

## Hard constraints

- **Everything open source.** Postgres, Cube Core (Apache-2.0), FastAPI, React/Vite, rdflib,
  rank-bm25, structlog. The OpenAI API is used for embeddings/generation and is **pluggable**;
  the app must boot and serve retrieval, facets, and all table views with no key.
- **`.env` is gitignored and this repo is public.** Never commit a key, never log one, never echo
  one in an error message or test fixture.
- **No fabricated numbers.** Every metric, count, accuracy figure, or latency in any README,
  results file, docstring, or UI copy must come from a command that actually ran, with the command
  shown alongside. Not yet measured → write "not yet measured". A plausible invented number is
  worse than a blank.
- **TDD.** Write the test, run it, confirm it fails for the stated reason, implement, run again,
  confirm it passes. A test that passes before its implementation exists is a broken test.
- **Push only completed, green issues.** No WIP commits on main. Each push is a working increment
  with its acceptance criteria met.
- **Close each issue when its AC are verified by running**, not by reading the code.

## Design system

`docs/DESIGN.md` is the Linear design system, machine-readable. Implement against those tokens:
canvas `#010102`, surface panels `#0f1011`, hairlines `#23252a`, ink `#f7f8f8`, and the single
lavender accent `#5e6ad2` used **only** on focus rings, the brand mark, and intentional CTAs —
never decoratively. Dense, quiet, precise. It should read as an instrument.

UX is a first-class requirement, not polish at the end:

- **Keyboard-first.** Every primary action reachable without a mouse. `/` focuses search,
  `j`/`k` move through results, `?` shows shortcuts.
- **Every number carries its denominator.** Always, everywhere. `n=8`, not a bare percentage.
- **Counts below threshold, percentages above.** "6 of 8" never renders as "75%" — a percentage
  implies precision the sample doesn't support.
- **Loading, empty, and refusal states are designed**, not defaulted. Refusal is its own visual
  state, distinct from "no results".
- **Drill-through from any aggregate to source clauses is mandatory.**
- **Show the resolved query** above every agent answer — `median RTF · healthcare · $200M–1B · n=8`
  — so a domain expert can catch a misinterpretation.

## Things that are easy to get wrong

**Model deal points LONG, not wide.** `deal_points(matter_id, deal_point_name, position, source_span,
updated_at)`. With the long shape, `deal_point_name` is a Cube *dimension* and a 93rd deal point is
just rows — no schema migration, no YAML edit, no UI change. Wide shape makes every new deal point a
three-place change.

**MAUD's annotations ARE the product data.** Do not re-extract what lawyers already labeled. Load
the labels directly. Extraction is a *separate calibration experiment*: run our extractor over a
held-out MAUD slice, compare to labels, publish the accuracy table. That is what makes the
generalization claim testable instead of asserted.

**FOLIO industry codes on CUAD are INFERRED.** CUAD ships no industry metadata. Label inferred
fields as inferred in the schema, the Cube `description`, and the UI. Never present them as ground
truth. This is the largest source of quiet error.

**Filter *values* are not enum-constrained.** Measure and dimension *names* can be locked with
structured-output enums. Values cannot — the model may emit `"Health Care"` when the data holds
`"Healthcare"`, returning zero rows that look exactly like "no comparable deals". Resolve every
filter value against the dimension's actual distinct values (exact → alias → embedding nearest) and
**fail loudly** rather than returning empty. This is the nastiest failure mode in the design.

**Never `count_distinct_approx`.** HyperLogLog is approximate. Fatal for a tool whose claim is
defensible numbers.

**Medians need explicit SQL.** There is no `type: median`. Use `percentile_cont(0.5) WITHIN GROUP`.
Reaching for `type: avg` yields a wrong number that looks right — reverse-termination-fee mean and
median diverge substantially.

**min_n does three jobs.** Statistical honesty; extraction-confidence gating; and **k-anonymity** —
an attorney who can filter until n=1 has extracted one client's negotiated term through the
analytics layer, around the ethical wall, without retrieving a document. Treat it as a
confidentiality control, not a nicety.

**FOLIO is 18,000+ concepts.** Map five or six dimensions. Do not attempt the ontology.

## Logging

structlog, JSON lines to `logs/explorer.jsonl` and stdout. Every request gets a bound `request_id`.
Log with timing: each LLM call (model, tokens, latency, cost), each Cube query (measures,
dimensions, filters, row count, latency), each ingest step (source, rows upserted, sha256). Never
log secrets or full document text. The Admin tab tails this file — that's why the format is JSONL.

## Layout

```
backend/explorer/
  ingest/     FOLIO loader, MAUD parser, EDGAR enrichment, CUAD parser, CLI
  folio/      ontology queries, hierarchy, code resolution
  retrieval/  embeddings + cache, BM25, hybrid, comparable ranking
  agent/      NL -> Cube selection (enum-constrained), filter-value resolution
  evals/      harnesses + metrics + calibration experiment
  api/        FastAPI routes, logging middleware, error envelope
cube/model/   the governed metric vocabulary — measure names are the eval's label space
frontend/src/
  views/      Explore · DealTerms · Coverage · Tables · Admin · Label
  components/ design-system primitives from docs/DESIGN.md
data/         downloaded corpora (gitignored; provenance in docs/provenance.md)
docs/results/ committed eval + calibration output
```

## Conventions

- Python 3.12, type hints on all public functions, `ruff`, `mypy`
- TypeScript strict, no `any`
- pytest (mark API-key tests `needs_key`), Vitest for frontend
- Conventional commits, one logical change each, `Closes #N`
- No new dependency without a one-line `# why` where it's declared

## Provenance

Every dataset records the exact download command, filename, byte size, and `shasum -a 256` in
`docs/provenance.md`. Clause and deal-point rows carry `source_file`, `source_contract_title`,
`char_start`, `char_end`. A row whose text cannot be traced to a byte range in the downloaded
source is a bug.

MAUD and CUAD are CC BY 4.0; FOLIO is CC BY. Attribution belongs in `docs/provenance.md` and the
README.

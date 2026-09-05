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
EDGAR (SIC industry · deal value · dates · parties, for the same 152)
SIC crosswalk (data/mappings/sic_to_folio.csv — SIC prefix -> industry code + label)
   │
   ▼  idempotent ingest, provenance recorded
Postgres ──► Cube Core (measures + industry dimensions, defined once in YAML)
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
| **Coverage** | KM | industry × deal-size grid; **thin cells are the signal, style them prominently** |
| **Tables** | you | browsable raw tables, sort/filter/paginate — so nobody opens psql |
| **Admin** | you | ingest status, calibration table, eval results, **live log viewer** |
| **Label** | KM | a review queue ranked by extractor disagreement; decisions are graded into the next calibration run |

## Hard constraints

- **Everything open source** except the model. Postgres, Cube Core (Apache-2.0), FastAPI,
  React/Vite, rank-bm25, structlog. The OpenAI API is used for embeddings, extraction and
  measure selection, and **an API key is required** to run the product.
  This used to say the app must boot and serve everything with no key. That constraint was
  written when nothing in the app called a model, so it cost nothing to keep. It costs
  something now: the model sits on the user's path in Ask, and a build that guarantees
  everything works without a key is a build whose headline feature is the one thing that does
  not. Tests that make a real call stay marked `needs_key` so CI holds no secrets, which is a
  property of the test suite and not a promise about the product.
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

**`frontend/src/styles/tokens.css` is the authority on colour**, and it is **GitHub Primer,
light** — canvas `#f6f8fa`, panels `#ffffff`, hairlines `#d1d9e0`, ink `#1f2328`, accent
`#0969da` used **only** on focus rings, the brand mark, and intentional CTAs, never
decoratively. Dense, quiet, precise. It should read as an instrument.

Light, not dark, because Deal Terms is a *reading* surface: dense monospace contract prose at
12–13px is materially easier to read dark-on-light. Do not restore the dark palette.

`docs/DESIGN.md` was a vendored 3,031-word spec for Linear's dark marketing site; #45 replaced
it with a one-page note recording the density and component-shape rules the code actually
follows — 4px base unit, one 6px radius, hairline borders and no elevation scale — and pointing
at `tokens.css` as the authority. It is a summary of the code, not a spec the code owes
anything to. When the two disagree, `tokens.css` is right and `DESIGN.md` is stale.

Every ink token clears WCAG 2.1 AA on `--surface-1`; `--ink-tertiary` (#6e7781, 4.6:1) is the
floor and carries the sample-size meta lines. Nothing lighter ships. No new hardcoded hex in
components — the only two in the codebase are the Admin status dots, and they are commented.

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

**Industry codes are INFERRED.** Neither MAUD nor EDGAR ships one; every code comes from the SIC
crosswalk, so it is classifier output. Label inferred fields as inferred in the schema, the Cube
`description`, and the UI. Never present them as ground truth. This is the largest source of quiet
error.

**Filter on the code, never the display label.** `industries.code` is opaque and stable; the label
is display text. A label drifting from "Health Care Industry" to "Healthcare" returns zero rows,
which reads as *we have no comparable deals*. This is the one property the ontology was earning and
the crosswalk delivers it (#49).

**Filter *values* are not enum-constrained.** Measure and dimension *names* can be locked with
structured-output enums. Values cannot — the model may emit `"Health Care"` when the data holds
`"Healthcare"`, returning zero rows that look exactly like "no comparable deals". Resolve every
filter value against the dimension's actual distinct values (exact → embedding nearest) and
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

## Logging

structlog, JSON lines to `logs/explorer.jsonl` and stdout. Every request gets a bound `request_id`.
Log with timing: each LLM call (model, tokens, latency, cost), each Cube query (measures,
dimensions, filters, row count, latency), each ingest step (source, rows upserted, sha256). Never
log secrets or full document text. The Admin tab tails this file — that's why the format is JSONL.

## Layout

```
backend/explorer/
  ingest/     MAUD parser, EDGAR enrichment + industry seed, CLI
  retrieval/  embeddings + cache, BM25, hybrid, comparable ranking
  agent/      NL -> Cube selection (enum-constrained), filter-value resolution
  evals/      harnesses + metrics + calibration experiment
  api/        FastAPI routes, logging middleware, error envelope
cube/model/   the governed metric vocabulary — measure names are the eval's label space
frontend/src/
  views/      Explore · DealTerms · Coverage · Tables · Admin · Label
  components/ design-system primitives; tokens in styles/tokens.css
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
`docs/provenance.md`. Deal-point rows carry `source_file`, `source_contract_title`,
`char_start`, `char_end`. A row whose text cannot be traced to a byte range in the downloaded
source is a bug.

MAUD is CC BY 4.0. The industry codes in `data/mappings/sic_to_folio.csv` came from FOLIO
(CC BY) before #49 removed the ontology; the attribution stays in `docs/provenance.md`.

---

# Iteration rules

**This is the operating loop. Follow it per issue, in order, without pausing between issues.**

Work issues in ascending number order (`#1 → #32`); the order is dependency-driven. Read the
body first: `gh issue view <N> -R xbt-a4224j/clause-explorer`. Acceptance criteria live there.

## The loop

1. **Write the test first.** Then RUN it and confirm it fails *for the stated reason* — not
   for an import error you did not intend. A test that passes before its implementation
   exists is broken; fix the test, not the gate.
2. **Implement** the minimum that satisfies the acceptance criteria.
3. **Run the gates** (below). All must be green.
4. **Verify against the running stack**, not just unit tests. Curl the endpoint, load the
   page, read the container logs. Unit tests passing is not evidence the feature works.
5. **Append to `docs/worklog.md`** (gitignored, local journal) — what was built, the commands run with their *real
   output*, any decision made (with rationale and accepted cost), and anything not done.
6. **Commit AND PUSH**, message ending `Closes #N`. One issue per commit so each diff
   maps to its ticket. **Push every time — never batch pushes across issues.** Work that
   is committed but unpushed is invisible to anyone reviewing the repo, and a reviewer
   looking at GitHub is the audience this repo exists for.
7. **Go straight to the next issue.** Do not stop to report or ask.

## Gates — every one, before every commit

```bash
# backend
ruff format --check . && ruff check .
mypy backend/explorer --ignore-missing-imports
env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"

# frontend, when touched
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

If a gate fails, the commit does not happen. **Never** weaken a gate, lower a threshold, or
narrow an acceptance criterion to make something pass. If a target genuinely cannot be met,
stop and say why.

## Environment

- **Python 3.12** — `psycopg-binary` has no wheel for 3.14, which `python3 -m venv` picks by
  default. Use `.venv` in the repo root.
- `python -m explorer.*` needs `PYTHONPATH=backend`. pytest gets it from `pytest.ini`;
  `make migrate` sets it. Bare module runs do not — a missing PYTHONPATH fails *silently*
  if you grep the output.
- DB: `CLAUSE_EXPLORER_DB=postgresql://explorer:explorer@localhost:5432/explorer`
- Real e2e tests using the API key are welcome — keep to ~4, mark them `needs_key`, and they
  are excluded from the CI gate automatically.

## Recording decisions

`docs/worklog.md` (gitignored, local) has a decisions table. Add a row whenever you make a call that a reviewer
might question. Record **the cost you accepted**, not just the choice — a decision without
its downside reads as marketing. Include decisions that turned out wrong.

## When a test fails, diagnose before fixing

Sometimes the test is wrong, not the implementation. Both have happened here already:
`PydanticUndefinedAnnotation` was a test-scope bug, while the `updated_at` failure was a
genuine schema defect that would have silently served stale aggregates. Read the actual
error before changing anything.

## Known traps in this codebase

- **Secret-shaped literals in tests** trip secret scanners and GitHub push protection even
  when obviously fake. Assemble fixtures at runtime: `"sk" + "-proj-" + "a" * 20`.
- **`from __future__ import annotations` + a pydantic model defined inside a function** →
  `PydanticUndefinedAnnotation`. Define request models at module scope.
- **FastAPI cannot build a response model from a union of `Response` subclasses.** Pass
  `response_model=None` on those routes.
- **structlog processors are typed against `MutableMapping`**, not `dict`; mypy rejects `dict`.
- **`ruff format` collapses multi-line signatures**, so multi-line string replacement against
  formatted files is fragile. Match a single line, or edit before formatting.
- **Postgres `now()` is transaction-start time.** Use `clock_timestamp()` in touch triggers.
- **Neither `api` nor `web` bind-mounts source.** `docker compose restart <svc>` silently
  serves the code baked into the old image — a route that exists 404s, and frontend changes
  are simply absent from the browser. Always `docker compose up -d --build <svc>`, and
  verify by grepping the *served* bundle, not the local `dist/`.
- **`up --build` is not always enough for `web`.** The Dockerfile runs `npm run build` inside
  the image, and Docker has reused that layer while source had changed — the container served
  a bundle with *some* recent work and not the newest, which is worse than serving nothing
  because it looks like a code bug. If a string you just added is missing from the bundle,
  `docker compose build --no-cache web`. Grep **inside the container**
  (`docker compose exec -T web grep -c ...`), not over HTTP, so nginx caching cannot confuse
  the diagnosis.
- **Tests that assert on bare `getByText` break when explainer prose is added.** Three have
  now broken this way. Scope assertions to a `data-testid` container; the text being unique
  was always an accident.

## The demo scripts are the acceptance test

`docs/demo-scripts.md` defines three walkthroughs. Every implementation decision is judged by
whether it makes one of them land. A feature serving none of them is out of scope; a rough
edge on one of their paths is a bug, not polish.

## Checkpoints — report, then keep going

After **#5**, **#11**, **#18**, **#23**. Report real numbers at each. #11 is the one that
matters most: it reveals whether the corpus actually supports the product. If facet cells come
back too thin for Script 1, say so plainly rather than proceeding as if it worked.

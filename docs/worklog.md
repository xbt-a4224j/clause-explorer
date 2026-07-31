# Work log

Progress and decisions, appended as issues close. Two rules:

1. **Every number here came from a command shown alongside it.** Nothing is estimated.
2. **Decisions are recorded with their rationale and their cost**, not just the outcome —
   including the ones that turned out wrong.

Guiding constraint: `docs/demo-scripts.md` is the acceptance test for the product. Decisions
are judged by whether they make one of those three scripts land.

---

## Decisions

| # | Decision | Why | Cost / risk accepted |
|---|---|---|---|
| D1 | `/healthz` reports **per dependency**, not a rolled-up boolean | The only useful thing the endpoint tells an operator is *which* dependency is down | Slightly larger response; callers must read `status` not just HTTP 200 |
| D2 | DB exception text is swallowed, never surfaced in the health response | The DSN carries credentials and the endpoint is unauthenticated | Loses detail at the boundary; the reason is logged server-side instead |
| D3 | Local venv pinned to **Python 3.12** | `psycopg-binary==3.2.3` publishes no wheel for the 3.14 that `python3 -m venv` picks by default | Contributors need 3.12 available |
| D4 | Production frontend build uses a separate `tsconfig.build.json` excluding specs | Specs referenced test globals and broke the Docker build; but they must still be type-checked | Two tsconfigs to keep in sync |
| D5 | Redaction is a **structlog processor**, not a call-site convention | A secret must not be able to reach the sink because one call site forgot to sanitize | Every log event pays a regex pass |
| D6 | Secret test fixtures are **assembled at runtime**, never literals | A credential-shaped literal in a public repo trips secret scanners and GitHub push protection even when obviously fake | Test code is marginally less readable |
| D7 | Request id binds to **contextvars** | Nested calls inherit it without threading a logger through every signature | Context must be cleared per request or it leaks across them |
| D8 | `deal_points` is **LONG**, one row per matter × deal point | MAUD ships 92 deal points and the ABA revises them; wide makes each addition a migration + Cube edit + UI change. Long makes it rows, and lets `deal_point_name` be a Cube dimension so new values surface automatically | Queries need a pivot for display; slightly more rows |
| D9 | Inferred values flagged **in the schema** (`is_inferred_*`), not only in docs | CUAD ships no industry metadata, so FOLIO codes there are classifier output. Unflagged, they are indistinguishable from MAUD gold and every aggregate silently mixes them | A flag column per inferrable field |
| D10 | Trigger uses **`clock_timestamp()`**, not `now()` | `now()` is transaction-start time and constant within a transaction, so insert-then-update in one ingest transaction would leave `updated_at` unchanged — Cube's `refresh_key` would serve stale aggregates with no way to notice | Timestamps are not transaction-consistent, which is correct here |
| D11 | Plain `schema.sql` + a tiny runner instead of Alembic | One schema, no release history to migrate across; a single readable SQL file reviews better than a generated revision chain | If the schema starts evolving across releases, this must become Alembic |
| D14 | Tab order in `tabs.ts` is **load-bearing** — number shortcut is the array index | One source of truth for order, label and shortcut; no parallel mapping to drift | Reordering the array silently rebinds every shortcut; noted in the file |
| D15 | Global shortcuts are **suppressed inside editable targets** (except Escape) | Without the guard, typing "3" into search jumps to Coverage — the demo dies on camera | Escape needs an explicit carve-out to still close overlays from an input |
| D13 | Internal errors return a **generic** message; the cause is logged instead | A traceback can carry the DSN or an API key and these endpoints are unauthenticated | Callers lose detail; the request id is the bridge to the real cause |
| D12 | FOLIO ancestry **denormalized** into `level_1/2/3_code` | Cube facet queries read them directly instead of walking a recursive CTE per query (#13) | Must be recomputed if the ontology reloads |
| D16 | FOLIO `code` is the **IRI suffix**, not the label or `dc:identifier` | IRIs are opaque and stable across releases; labels get retitled and `dc:identifier` is present on only part of the ontology | Codes are unreadable in psql; every display needs a join to `label` |
| D17 | Multi-parent concepts keep **one** parent — the lexicographically smallest code | FOLIO is a DAG: 830 of 18,327 classes declare 2+ `rdfs:subClassOf`. `parent_code` holds one, and the tie-break must be deterministic or reloads reshuffle the hierarchy | For those concepts the roll-up path in the UI is *one* true path, not the only one. A closure table would fix it at the price of a join in every Cube dimension — revisit if a mapped dimension (#9) lands on a multi-parent branch |
| D18 | **DEPRECATED and SANDBOX subtrees excluded** from the load | Dead vocabulary that nothing is tagged with; `resolve()` returning one of those codes produces zero rows that read as "no comparable deals" — the exact failure #25 exists to prevent | Row count is 18,259 not 18,327; if FOLIO revives a deprecated branch we silently miss it |
| D20 | Span for a discontinuous excerpt is the **enclosing range** first-segment-start .. last-segment-end | MAUD joins separate provisions with `<omitted>`; per-segment spans need a second table, and the schema has one span per deal point | The range contains material the annotator did not quote. Accepted: a drill-through that opens the right provisions with surrounding text beats one that cannot open at all |
| D21 | Unlocatable spans store **NULL** (495 of 12,937) | An offset that is wrong opens the wrong clause and looks completely right; "no fabricated numbers" applies to byte ranges | 3.8% of rows have no drill-through until the locator improves |
| D22 | SIC -> FOLIO crosswalk is a **checked-in CSV** with longest-prefix resolution | It is curation, not logic; a reviewer must be able to fix one row without reading Python, and 4-digit rows can override a 2-digit group (software 737x -> Information, where NAICS puts it) | Two places to look when an industry looks wrong: the file and the resolver |
| D23 | Every EDGAR-derived industry is **`is_inferred_industry = TRUE`** | SIC is coarse and self-assigned, the crosswalk is a judgement, and identification picks the acquirer in ~15% of cases | Nothing in the product can present industry as gold; the UI must flag it everywhere |
| D24 | The identified company is **the first party that resolves to a registrant with an SIC**, subs excluded | MAUD is a public-target study, so the target is an SEC registrant; this took CIK resolution from 97/152 to 134/152 | Picks the acquirer in 3 of 20 hand-checked matters, which then carry the acquirer's industry |
| D25 | `deal_value_usd` left **NULL** rather than estimated | EDGAR's company endpoints do not carry transaction value; price x shares is an estimate of a different order and would appear in the UI as fact | #9 stays open, `deal_size_band` is empty, and demo script 1's size filter has nothing to filter on |
| D26 | CUAD contracts are **not** rows in `matters`; their clauses carry `matter_id` NULL | `matters` is the comparable-deals universe a partner filters. 510 commercial contracts in there would inflate every facet count that reads as "comparable deals" | CUAD clauses have no matter card to drill into; they stand on `source_contract_title` and `source_file` |
| D27 | CUAD clause id includes **`char_end`** | 242 annotations share a start offset with another of the same category and differ only in length; keying on start alone collapsed 244 distinct expert spans | Ids change if CUAD re-cuts an annotation — which is why the load prunes rows the corpus no longer produces |
| D28 | The CUAD load **prunes** `corpus='cuad'` rows the parse no longer produces | Upsert alone is not idempotent across a corpus revision: a superseded row survives forever and keeps answering drill-throughs with text nothing points at | A parse bug that drops rows also deletes them from the table; the scope is limited to `corpus='cuad'` so MAUD can never be touched |
| D29 | Every upsert carries an **`IS DISTINCT FROM` guard**; only genuinely changed rows are rewritten | Cube's `refresh_key` is `MAX(updated_at)`, so an unconditional upsert makes a no-op re-ingest invalidate every cached aggregate | Longer, noisier SQL in four loaders, and the guard column list must be kept in step with the column list above it |
| D30 | Pharma, biotech, devices and CROs are grouped under **Health Care**, departing from NAICS | A partner asking for healthcare comparables means them; straight NAICS leaves Health Care at n=3 of 152 | The dimension is our definition, not a standard one. Flagged in every affected `basis` cell, the file header, a pinning test, and required in UI copy |
| D31 | `numeric_value` is parsed from MAUD's own answer text at ingest | The numbers are inside the expert's label ("4 business days"), so reading them is normalisation, not extraction — and without it there is nothing to take a median of | Units differ per deal point, so the column is meaningless unless `deal_point_name` is filtered first; the model's descriptions say so |
| D32 | Answers that only bound a value store **NULL** | "Greater than 5 business days" is an inequality; storing 5 puts it in a median looking like a measurement | 809 numeric rows instead of slightly more, and some real information is dropped rather than distorted |
| D33 | The single `type: avg` is named **`mean_numeric_value_do_not_use_for_market`** | It exists only to show divergence from the median; an agent selecting by name cannot reach for it casually | An ugly name in a public API surface — deliberately |
| D34 | Embeddings are **256-dim float16**, not the model's native 1536-dim float32 | The cache is committed to a public repo; native size would be ~86 MB against a measured 9.5 MB | Some retrieval quality, unmeasured until #17's ablation quantifies it |
| D35 | The committed cache is written **only** by `warm_cache`, never by a query path | A developer with a key would otherwise rewrite a version-controlled artefact just by searching, producing a diff from nowhere | A miss with a key is cached in memory only, so it is re-embedded next process start |
| D19 | Aliases live in a separate **`folio_aliases`** table; an ambiguous alias resolves to `None` | `skos:altLabel` is many-per-concept, and picking arbitrarily between two concepts sharing an alias is a wrong answer that looks right | An extra table and a second query on the resolve miss path |
| D36 | The facet rail carries the **FOLIO code** beside every industry label, and `/comparables` is filtered by the code | The label is a display string; matching on it is the silent-empty-result failure #25 exists for. A code is the join key and cannot drift from "Health Care Industry" to "Healthcare" | `comparable_deals.code` had to become public in the Cube view, widening the agent's selectable surface by one dimension it should never display |
| D37 | A facet group whose only values are `unknown`/`unclassified` renders **disabled with a stated reason**, not hidden | Omitting deal size claims the corpus has no size axis; showing it enabled offers a filter that cannot narrow anything. Both are false in different directions | A `REASONS` map in `facets.py` keyed by group — one hand-written string that must be deleted when #9 lands, and nothing fails if it is not |
| D38 | Explore does **no** client-side filtering of the ranked response | The server is the authority on the slice. Filtering the response in the browser put the visible list and `candidate_count` into disagreement, and ranked against a corpus the partner never asked about | The UI cannot cheaply preview a filter without a round trip |
| D39 | Clause text is the **exact slice** of the source file at the recorded offsets, never a summary | The provenance rule: a row whose text cannot be traced to a byte range in the source is a bug. A paraphrase is untraceable by construction | The card renders raw contract text including page-break artefacts; it scrolls in its own box rather than being cleaned up |
| D40 | A deal point with no resolvable span returns **null text plus a reason**, in three distinct flavours | An empty box reads as "there is no such clause"; the truth is "MAUD located no range", "the corpus is not on disk", or "the range is out of bounds" | Three strings to keep accurate, and the card must render all three |
| D41 | The pasted summary is built **server-side** | It leaves the app and loses every visual qualifier, so the inferred flag and the denominator have to survive as words. Building it in the client would let the two drift | The paragraph cannot be restyled per view; changing its wording is a backend change with a test |
| D45 | Palette switched from Linear dark to **GitHub Primer light**; `tokens.css` is the authority and `docs/DESIGN.md`'s colour values are superseded | Deal Terms is a reading surface — dense monospace contract prose at 12–13px reads materially better dark-on-light. Theming was already token-only (a grep found two literal hexes in the whole frontend), so the swap cost three lines beyond the token file | `docs/DESIGN.md` now disagrees with the code on colour while remaining authoritative on spacing and density — a split source a reader has to be told about, so CLAUDE.md states it. Two Admin status dots had to be rechosen by hand |
| D42 | The count-vs-percentage switch is decided **per row on `answered_n`**, not per selection | How many of the selected matters answer *that* deal point is the real sample size; a selection-level switch renders `29 of 29` as a percentage because the selection happened to be 40 | Two rows in the same response can be rendered in different forms, which looks inconsistent until you read the denominators |
| D43 | The display string is **pre-rendered server-side** | One implementation of the rule, so a table cell, a tooltip and a pasted paragraph cannot disagree about when a percentage is allowed | The client cannot reformat for a narrow column; changing the wording is a backend change |
| D44 | Every row carries its **full position distribution**, not just present/absent | `present_count` is right for Yes/No deal points and misleading for graded ones — "8 of 8 present" says nothing about Constructive vs Actual knowledge | Rows are heavier and the view has a second line of detail under each headline |

---

## Progress


## #1 — Stack boots: Postgres + Cube Core + FastAPI + web via compose

Four services under compose, each healthchecked. `/healthz` reports **per dependency**
rather than a single boolean — the only useful thing the endpoint can tell an operator is
*which* dependency is down. Status is `ok` only when all are reachable, `degraded` otherwise.

Frontend is a minimal shell that fetches `/api/healthz` through the nginx proxy, proving the
fourth service builds and the proxy path works. The six-tab shell and keyboard nav are #5.

### Verification

```
$ docker compose ps --format 'table {{.Service}}\t{{.Status}}'
SERVICE   STATUS
api       Up 3 seconds (health: starting)
cube      Up 3 seconds
db        Up 9 seconds (healthy)
web       Up 3 seconds

$ curl -s localhost:8000/healthz
{"status":"ok","db":"ok","cube":"ok","version":"0.1.0"}

$ curl -s localhost:5173/api/healthz          # through the nginx proxy
{"status":"ok","db":"ok","cube":"ok","version":"0.1.0"}

$ curl -o /dev/null -w '%{http_code}' localhost:4000   # cube playground
200

$ docker compose down && docker compose up -d          # no manual step
{"status":"ok","db":"ok","cube":"ok","version":"0.1.0"}

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
4 passed in 0.35s

$ cd frontend && npx vitest run
Test Files  1 passed (1) / Tests  3 passed (3)

$ ruff format --check . && ruff check .
11 files already formatted / All checks passed!

$ mypy backend/explorer --ignore-missing-imports
Success: no issues found in 9 source files

$ cd frontend && npx tsc --noEmit
(clean)
```

With nothing running, `/healthz` correctly self-reports rather than lying:
`{"status":"degraded","db":"unreachable","cube":"unreachable","version":"0.1.0"}`

### Notes

- Local venv pinned to **Python 3.12** — `psycopg-binary==3.2.3` publishes no wheel for 3.14.
- Production frontend build uses `tsconfig.build.json` (excludes specs); `tsconfig.json`
  still type-checks specs for `make check`, so both paths stay covered.
- Two `except Exception` in the health checks carry `# noqa: BLE001` with rationale: a health
  check must never propagate, and the DB exception text contains the DSN credentials on an
  unauthenticated endpoint.

### Not done

- No dependencies added beyond `requirements.txt` as filed.

---

## #2 — Structured JSON logging with request context and secret redaction

structlog → JSON lines to stdout and `logs/explorer.jsonl`. JSONL specifically so the Admin
tab (#30) can tail and parse into columns without a log service.

**Redaction is a processor, not a call-site convention.** It runs over every event and every
string value immediately before rendering, so a secret cannot reach the sink by being passed
to a call site that forgot to sanitize. Covers OpenAI-style keys (project and legacy), DSN
passwords (username preserved so the line stays diagnosable), and bearer tokens.

**Request id binds to contextvars**, so nested calls inherit it without threading a logger
through every signature. Inbound `x-request-id` is honoured, otherwise generated; echoed back
as a response header.

Domain helpers (`log_llm_call`, `log_cube_query`, `log_ingest_step`) so field names and timing
stay consistent across the codebase rather than drifting per call site.

### Verification

```
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
13 passed in 0.46s

$ ruff format --check . && ruff check .
All checks passed!

$ mypy backend/explorer --ignore-missing-imports
Success: no issues found in 10 source files
```

Live JSONL from the running container, with an inbound request id honoured end to end:

```
$ curl -H "x-request-id: demo-req-42" localhost:8000/healthz
$ docker compose logs api --tail 6
{"method":"GET","path":"/healthz","event":"request_start","request_id":"demo-req-42","level":"info","timestamp":"2026-07-30T16:18:05.416967Z"}
{"method":"GET","path":"/healthz","status":200,"duration_ms":14.2,"event":"request_end","request_id":"demo-req-42","level":"info","timestamp":"2026-07-30T16:18:05.431111Z"}

$ curl -D- -o /dev/null -H "x-request-id: demo-req-42" localhost:8000/healthz | grep -i x-request-id
x-request-id: demo-req-42
```

### Notes

- Test fixtures for secrets are **assembled at runtime**, never written as literals. A
  credential-shaped literal in a public repo trips secret scanners and GitHub push
  protection even when obviously fake.
- `_redact_processor` is typed against `MutableMapping`, which is structlog's actual
  processor contract — `dict` fails mypy against the declared `Processor` type.
- Two `except Exception` in the health checks keep `# noqa: BLE001` with rationale.

### Not done

- No dependency changes; `structlog` was already in `requirements.txt` as filed.

---

## #3 — Postgres schema + migrations

Six tables: `folio_concepts`, `matters`, `deal_points`, `clauses`, `labels`, `ingest_runs`.
Applied via `schema.sql` and a small runner (`python -m explorer.db.migrate up|down|reset`).

The load-bearing decision is **D8**: `deal_points` is long. Tests assert it directly — one
checks there are no per-deal-point columns, another inserts a deal point name invented by the
test and requires it to work with no schema change.

### Verification

```
$ python -m explorer.db.migrate up && ... down && ... up      # round-trip
{"event": "migrate_up"} / {"event": "migrate_down"} / {"event": "migrate_up"}

$ pytest backend/tests/test_schema.py -q
18 passed in 0.29s

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
31 passed in 0.60s

$ ruff format --check . && ruff check .   ->  All checks passed!
$ mypy backend/explorer --ignore-missing-imports  ->  no issues in 12 source files
```

Extensibility proof — five deal point names inserted, none of them anticipated by the schema:

```
distinct deal_point_name values: 5
columns on deal_points        : 9 (unchanged)
```

### A real bug this caught

`updated_at` did not advance on update. Cause: Postgres `now()` returns **transaction** start
time and is constant for the transaction, so an insert followed by an update in one ingest
transaction left the timestamp untouched — which would have left Cube's `refresh_key` serving
stale aggregates with no visible symptom. Fixed with `clock_timestamp()` (D10). The test that
caught it asserts `after > before`, not merely that the column exists.

### Notes

- `python -m explorer.db.migrate` needs `PYTHONPATH=backend`; pytest gets it from `pytest.ini`.
  Added a `make migrate` target so the path is not a thing to remember.
- Schema tests **skip** rather than fail when Postgres is unreachable, so CI stays green on an
  environment problem rather than reporting a false schema failure.

### Not done

- No dependencies added.

---

## #4 — Uniform error envelope

Every non-2xx response is `{"error": {"code", "message", "detail"}}`, so the frontend has one
error path instead of three (FastAPI's `detail` string, its validation array, and whatever an
unhandled exception renders as). Validation errors name the offending field — a bare
"validation error" is unactionable.

### Verification

```
$ pytest backend/tests/test_errors.py -q
8 passed in 0.30s

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
39 passed

$ curl -s localhost:8000/nope            # live, from the container
{"error":{"code":"not_found","message":"Not Found","detail":null}}
```

A test asserts the 500 path does **not** leak exception text (D13).

### A test bug worth recording

`test_validation_error_uses_the_envelope` failed with `PydanticUndefinedAnnotation`. Cause: the
request model was defined *inside* the test function, and under `from __future__ import
annotations` the parameter annotation is a string that pydantic cannot resolve against a local
name. Moved to module scope. The implementation was correct throughout — worth noting because
the first instinct was to change the handler.

### Not done

- No dependencies added.

---

## #5 — Six-tab shell, Linear tokens, keyboard navigation

Navigation, the keyboard contract and a live health strip. Panels are deliberately
placeholders — each view lands in its own issue (#19–#22, #29–#31).

Design tokens transcribed from `docs/DESIGN.md` into `styles/tokens.css`; `shell.css` uses
tokens only, no literal colors. Accent `#5e6ad2` appears on the brand mark, the active-tab
underline and focus rings — nowhere decorative.

Number-key affordances render **on the tabs themselves**, so the shortcut is discoverable
without opening the help overlay.

### Verification

```
$ npx vitest run
Test Files  1 passed (1) / Tests  10 passed (10)

$ npx tsc --noEmit        -> clean
$ npm run build           -> built in 302ms

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
39 passed

$ curl -o /dev/null -w '%{http_code}' localhost:5173     -> 200
```

Rendered against the live stack: six tabs, number affordances, status strip reading
`ok · db ok · cube ok · v0.1.0`.

### The test that matters most

`ignores shortcuts while typing in an input` — without the editable-target guard, typing
"3" into the search box switches to Coverage. That is a demo-killing bug and it is invisible
until someone types a digit on camera (D15).

### Not done

- Panels are placeholders by design.
- `j`/`k` result navigation is declared in the shortcut overlay but only becomes meaningful
  once Explore has a result list (#19). Listed there deliberately so the contract is fixed
  before views are written against it.

## #6 — FOLIO.owl loaded into folio_concepts with hierarchy

`rdflib` parse of the published `FOLIO.owl` into `folio_concepts` + a new `folio_aliases`
table, with ancestry denormalized at load time into `level_1_code`/`level_2_code`/
`level_3_code` so Cube dimensions (#13) read columns rather than walking a recursive CTE.

`resolve(text) -> code | None` is exact label → unique alias → `None`. **No fuzzy matching**
— that is #25's job, where a near-match is paired with an explicit "did you mean" instead of
a silent substitution.

### Verification

```
$ curl -sL -o data/folio/FOLIO.owl \
    https://raw.githubusercontent.com/alea-institute/FOLIO/main/FOLIO.owl
$ ls -l data/folio/FOLIO.owl
-rw-r--r--@ 1 daj staff 18335854 Jul 30 13:46 data/folio/FOLIO.owl
$ shasum -a 256 data/folio/FOLIO.owl
44657b4ed844f5f9c9c48869184606b4fc671471a8263d79d241de87809fa239

$ PYTHONPATH=backend python -m explorer.ingest.folio
{"source": "folio", "rows_read": 18259, "rows_upserted": 18259, "concepts_total": 18259,
 "aliases_total": 47523, "duration_ms": 4881.8,
 "sha256": "44657b4ed844f5f9c9c48869184606b4fc671471a8263d79d241de87809fa239",
 "event": "ingest_folio"}

$ PYTHONPATH=backend python -m explorer.ingest.folio    # second run — idempotent
{'rows_read': 18259, 'concepts_total': 18259, 'aliases_total': 47523}

$ # hand-checked branch, via explorer.folio.resolve
resolve('Health Care Industry') -> RCSG4k3ah1Pu5YgPexPgOmL
resolve('Hospitals Industry')   -> REDA36d2F98543EBb23B69ba
ancestors -> ['Industry and Market', 'Industry', 'Health Care Industry']
descendants of Health Care Industry: 91
level histogram: [(1,24),(2,858),(3,1328),(4,5630),(5,3035),(6,2962),(7,3708),(8,577),(9,117),(10,20)]

$ ruff format --check . && ruff check .     -> 22 files already formatted / All checks passed!
$ mypy backend/explorer --ignore-missing-imports  -> Success: no issues found in 16 source files
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
58 passed          # was 39; 19 new
```

### Row counts, stated exactly

The file declares **18,327** `owl:Class` nodes. **18,259** loaded. The 68 missing are
unlabelled classes (a class with no `rdfs:label` cannot be displayed or resolved) plus the
DEPRECATED and ZZZ-SANDBOX subtrees (D18). 47,523 aliases from `skos:altLabel`, which
includes FOLIO's translations — `resolve('Gesundheitswesen')` returns the Health Care
Industry code, verified above, at no extra cost.

### A finding that matters for #9 and #25

`resolve('healthcare')` returns **`None`**. The ontology's label is "Health Care Industry"
and "healthcare" is not among its altLabels. This is the CLAUDE.md filter-value failure mode
appearing at the very first opportunity, and it is *correct* behaviour for #6 — a miss is
visible, a fuzzy guess is not. Two consequences to carry forward:

- #9 must map SIC → FOLIO codes explicitly, never by matching industry name strings.
- #25 must handle the demo phrase "healthcare" (demo script 1's literal wording) via the
  alias/embedding resolution path, or script 1 returns zero rows.

### Schema change

Added `folio_aliases(alias, code)` and a `lower(label)` index on `folio_concepts`. Applied
with `make migrate`; `migrate down` drops `folio_aliases` before `folio_concepts` so the FK
does not block teardown.

### Not done

- No `dc:identifier` short codes (e.g. `AFS`) stored. NAICS-aligned identifiers are on the
  Industry branch and may be useful for #9's SIC mapping; deferred until #9 shows it needs
  them rather than guessing now.

## #7 — MAUD downloaded, with provenance

`scripts/download_maud.sh` fetches one archive, extracts it, and prints the checksum and
counts it just measured. `explorer/ingest/maud_corpus.py` is the single place that knows the
layout; `corpus_available()` is a bool probe so tests skip — with the fixing command in the
message — instead of failing on a clean checkout.

### Verification

```
$ ./scripts/download_maud.sh
sha256: 75af5a33d038e9254864f043da38072490ffe11e8488d58d0a2dd39c8f554519
archive bytes: 32893590
contract files: 152
extracted bytes: 202424 KiB

$ find data/maud/data -type f | wc -l
     158
$ du -sh data/maud/data/contracts | cut -f1
52M

$ pytest backend/tests/test_maud_corpus.py -q
5 passed in 0.70s

$ mv data/maud/data /tmp/maud_hidden && pytest backend/tests/test_maud_corpus.py -q -rs
SKIPPED [1] ... MAUD corpus not downloaded — run scripts/download_maud.sh   (x4)
1 passed, 4 skipped in 0.01s

$ ruff format --check . && ruff check .   -> 24 files already formatted / All checks passed!
$ mypy backend/explorer --ignore-missing-imports -> Success: no issues found in 17 source files
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
63 passed          # was 58
```

### Measured corpus shape

- 152 contract texts, 53,464 KiB
- 39,231 label rows across the three CSVs
- **92** distinct `question` values — the ABA deal points, matching the documented count
- 7 categories; `data_type` splits main 20,623 / abridged 14,928 / rare_answers 3,680

### The source we did not use, and why

The Hugging Face mirror `theatticusproject/maud` was the first candidate and is the more
convenient API. It ships the same three label CSVs but only **100** of the 152 contract
texts — verified by downloading it: `contracts in csv: 152, with text file: 100, missing
text: 52`. Drill-through to source clauses is a hard requirement, and 52 matters that cannot
drill through is a broken product, so the GitHub `data.zip` is the source of record. One
archive also means one command and one checksum in provenance.

### Note carried into #8

MAUD's `label` column is an answer *index*, not a deal-point name. The deal point is
`question` (92 values); `text_type` is the coarser 22-value grouping and `category` the
7-value one. Reading `label` as the deal point would have produced 10 deal points instead
of 92 and looked plausible.

## #8 — MAUD parsed into matters + LONG deal_points

152 matters, 12,937 deal-point rows, 92 distinct `deal_point_name` values read from the
corpus rather than hardcoded. `is_inferred = false` on every row — these are the lawyers'
labels, and nothing here re-extracts them.

### Verification

```
$ PYTHONPATH=backend python -m explorer.ingest.maud
{"source": "maud", "matters": 152, "deal_points": 12937, "deal_point_names": 92,
 "spans_located": 12442, "spans_null": 495, "duration_ms": 8092.6, "event": "ingest_maud"}

$ PYTHONPATH=backend python -m explorer.ingest.maud      # second run — idempotent
{"source": "maud", "matters": 152, "deal_points": 12937, ... "duration_ms": 7640.6}

$ # against the loaded database
matters 152
deal_points 12937
distinct names 92
inferred rows 0
null spans 495
per-matter deal points min/avg/max: (75, 85.1, 90)
sample title: contract_1 | 'Exhibit 2.1 AGREEMENT AND PLAN OF MERGER among MERCK SHARP & DOHME CORP...'
Type of Consideration: All Cash 89 · All Stock 39 · Mixed Cash/Stock 21 · Mixed: Election 3

$ pytest backend/tests/test_maud_parse.py -q
16 passed in 8.31s

$ ruff format --check . && ruff check .   -> 27 files already formatted / All checks passed!
$ mypy backend/explorer --ignore-missing-imports -> Success: no issues found in 18 source files
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
79 passed in 16.66s          # was 63
```

### Source spans: 12,442 of 12,937 located (96.2%), 495 stored NULL

MAUD's excerpt text is **not** byte-identical to the contract file it came from, which the
AC's provenance requirement runs straight into. Three differences, found by measuring rather
than assuming — the naive `excerpt in source` check matches **0 of 300** sampled rows:

| Difference | Effect if ignored |
|---|---|
| files carry `________________` page-break rules the excerpts drop | full-excerpt match fails; only the first ~230 chars align |
| excerpts end with `(Page 40)` / `(Pages 9-10)` citations | tail anchor never matches |
| excerpts are discontinuous, joined by literal `<omitted>` | whole-excerpt anchoring impossible |

Located fraction as each was handled, measured over all 12,937 pairs:

```
exact match:                          0
whitespace-normalized, head+tail:  4,504   (34.8%)
+ page citations stripped:         8,391   (64.9%)
+ split on <omitted>, per-segment: 12,442   (96.2%)
```

The 495 that will not anchor store **NULL**, not a guess. `no fabricated numbers` covers
offsets: a wrong byte range is a drill-through that opens the wrong clause and looks right.

### Verified corpus facts

- Every (matter, deal point) pair has exactly **one** answer — 12,937 pairs, no multi-answer
  case — so `UNIQUE (matter_id, deal_point_name)` holds without a tie-break rule.
- 152 × 92 = 13,984 possible pairs; 12,937 exist. Coverage is 92.5%, not complete: matters
  carry 75–90 deal points each, mean 85.1. The LONG shape absorbs this with no NULL columns.
- Only `data_type='main'` rows load. `abridged` (14,928 rows) is the same annotation over a
  shortened passage and `rare_answers` (3,680) is keyed to a `<RARE_ANSWERS>` pseudo-contract;
  either would double-count matters in every rollup.

### A performance bug worth recording

The first working version took **~260 s** to parse. Cause: `locators.setdefault(matter_id,
SpanLocator(sources[matter_id]))` — Python evaluates `setdefault`'s default argument on
*every* call, so the whitespace index was rebuilt once per deal point (12,937 times) instead
of once per matter (152). An explicit `if key not in dict` took it to **8 s**. The profile
was flat and misleading until the locators were hoisted out of the loop; `setdefault` with a
constructor call is a trap, not a shorthand.

### Not done

- `source_contract_title` is the document's own opening line-run, trimmed to 200 chars — real
  bytes from the file. Party names, signing date and deal value come from EDGAR in #9; none
  are guessed here.
- `clauses` is untouched; MAUD gives deal points, and clause text rows come from CUAD (#10).

## #9 — EDGAR enrichment: industry, signing date, party names (deal value NOT done)

**This issue is not closed.** Four of its five field requirements are met and verified;
`deal_value_usd` is not populated and I am not checking that box. Detail below.

### Verification

```
$ ./scripts/download_edgar_index.sh
bytes: 39865365 · lines: 1052920
sha256: e3b9d73e3a3d696029b08a3b3589a6495cdcede98a3f70fdd832e1a6c25ca1fd

$ PYTHONPATH=backend python -m explorer.ingest.edgar
{"source": "edgar", "matters": 152, "with_target_name": 144, "with_signing_date": 149,
 "with_sic": 134, "with_folio_industry": 134, "network_requests": 142,
 "duration_ms": 70257.2, "event": "ingest_edgar"}

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
97 passed in 12.85s        # was 79
$ ruff format --check . && ruff check . && mypy backend/explorer --ignore-missing-imports
All checks passed! / Success: no issues found in 19 source files
```

### Coverage, measured (of 152 matters)

| field | resolved | source |
|---|---|---|
| `signing_date` | **149 (98.0%)** | the agreement's own header |
| `target_name` | **144 (94.7%)** | the agreement's own header |
| `sic_code` | **134 (88.2%)** | EDGAR submissions for the resolved CIK |
| `folio_industry_code` | **134 (88.2%)** | `data/mappings/sic_to_folio.csv` |
| `deal_value_usd` | **0** | not available from these endpoints — see below |

Industry distribution over the 152:

```
 42  Manufacturing            25  Finance and Insurance     18  (unresolved)
 18  Information              12  Real Estate/Rental        11  Mining and Natural Resources
  7  Business and Admin        3  Construction               3  Retail Trade
  3  Health Care               2  Professional Services      2  Wholesale Trade
  2  Accommodation and Food    2  Utilities                  1  Educational Services
  1  Transportation
```

Signing dates run **2020-03-13 → 2021-11-21**. `is_inferred_industry` is TRUE on all 134.

### Identification accuracy, hand-checked

Party identification improved in three measured steps:

```
first working version:                          97/152 CIK resolved
+ extend a match over a trailing legal suffix:  115/152    ("...SYSTEMS GROUP" -> "...GROUP, INC.")
+ try each non-sub party, accept the first
  that resolves to a registrant WITH an SIC:    134/152
```

A 20-matter random sample was checked by hand against the deals: **17 of 20** identified the
target, **3 of 20** identified the acquirer instead (contract_84 VICI/MGM Growth, contract_147
Macquarie/Waddell & Reed, contract_5 AstraZeneca/Alexion). Those three carry the *acquirer's*
industry. That is a real error, recorded rather than smoothed over, and it is part of why
`is_inferred_industry` is TRUE on every enriched row.

### deal_value_usd is not populated, and why

EDGAR's submissions API carries no transaction value — it is company metadata (SIC, name,
state, filing list). Deal value lives in the DEFM14A/8-K narrative or must be computed as
per-share consideration × shares outstanding, which is an *estimate* of a different kind from
everything else here. Rather than ship a number of unstated provenance under a column the UI
will present as fact, the column stays NULL and #9 stays open.

Consequence to face at the #11 checkpoint, not later: `deal_size_band` is empty, so demo
script 1's "$200M–1B" filter has nothing to filter on, and the Coverage grid (#22) has one
real axis instead of two.

### A corpus finding that matters more than the code

**Health Care is 3 matters of 152.** The crosswalk is right — pharma and biotech are SIC
2834/2836, which NAICS and FOLIO both place under Manufacturing, and FOLIO's Health Care
Industry is NAICS 62, providers — but a partner asking for "healthcare comparables" means
pharma too. Two honest options at #11: report the thin cell as the Coverage tab is designed
to (the product working), or add pharma SIC rows to the crosswalk and say plainly that we
widened the definition. Not decided here; recorded so the decision is visible.

Signing dates spanning **20 months**, not five years, is the second corpus limit. Any UI copy
saying "last five years" would be false.

## #10 — CUAD parsed into clauses

510 commercial contracts, 13,823 clause rows over 41 expert clause types, every offset read
from the corpus rather than reconstructed.

### Verification

```
$ ./scripts/download_cuad.sh
sha256: f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a
archive bytes: 18309308
files extracted: 5

$ PYTHONPATH=backend python -m explorer.ingest.cuad
{"source": "cuad", "contracts": 510, "clauses": 13823, "clause_types": 41,
 "with_industry": 0, "duration_ms": 452.0, "event": "ingest_cuad"}

$ PYTHONPATH=backend python -m explorer.ingest.cuad      # second run — idempotent
{"source": "cuad", "contracts": 510, "clauses": 13823, ... "duration_ms": 424.2}

$ # against the loaded database
clauses 13823 · clause types 41 · matters still 152 · gold-industry rows 0
top clause types: Parties 2554 · License Grant 777 · Cap On Liability 672 ·
                  Anti-Assignment 654 · Audit Rights 643

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
108 passed in 13.38s          # was 97
$ ruff format --check . && ruff check . && mypy backend/explorer --ignore-missing-imports
All checks passed! / Success: no issues found in 20 source files
```

### Corpus shape, measured

CUAD asks all 41 categories of all 510 contracts — 20,910 question rows, of which **6,702**
are answered, yielding **13,823** answer spans (a category can be answered with several
spans). Only answered categories become rows: an unanswered category means the clause is
*absent*, and a row with empty text would make "this contract has no audit-rights clause"
indistinguishable from "we have no text for its audit-rights clause".

### A bug the provenance test caught

The first id scheme was `sha256(title, category, char_start)`. Loading produced **13,579**
rows for 13,823 parsed clauses. The 244 missing rows were not duplicates: **242 CUAD
annotations share a start offset with another annotation of the same category and differ only
in length** — `Google` and `Google Inc`, both at offset 644 of the same contract. Two distinct
expert spans, silently collapsed into one. `char_end` is now part of the key.

This is the value of asserting loaded-row-count against parsed-row-count rather than "the
insert did not error".

### Industry is 0 of 13,823, deliberately

CUAD ships no industry metadata. `is_inferred_industry` is TRUE on every row and
`folio_industry_code` is NULL on every row, because nothing here guesses an industry from a
filename. A keyword table over contract titles would produce a column that looks populated
and is unmeasured; the classification pass belongs with the calibration work (#28) where its
accuracy is published. README's new Limitations section states this plainly, as the AC asks.

### Not done

- CUAD clauses have `matter_id` NULL. See D26 — they are a clause corpus, not deals.

## #11 — Idempotent ingest CLI with run tracking

`python -m explorer.ingest --source {folio,maud,edgar,cuad,all}`, run in dependency order
(FOLIO before MAUD because `matters.folio_industry_code` is a foreign key into it; MAUD before
EDGAR because enrichment updates rows MAUD creates).

### Verification

```
$ make ingest
PYTHONPATH=backend python -m explorer.ingest --source all
{"source": "folio", "rows_read": 18259, "rows_upserted": 18259, "duration_ms": 3893.0,
 "sha256": "44657b4ed844f5f9c9c48869184606b4fc671471a8263d79d241de87809fa239"}
{"source": "maud", "matters": 152, "deal_points": 12937, "spans_located": 12442, "duration_ms": 7298.4}
{"source": "edgar", "matters": 152, "with_sic": 134, "network_requests": 0, "duration_ms": 1245.0}
{"source": "cuad", "contracts": 510, "clauses": 13823, "duration_ms": 353.2}
{"sources": ["folio","maud","edgar","cuad"], "duration_ms": 12839.9, "event": "ingest_complete"}
real 13.3s

$ PYTHONPATH=backend python -m explorer.ingest --source nope
error: argument --source: invalid choice: 'nope' (choose from 'folio','maud','edgar','cuad','all')

$ mv data/cuad/CUADv1.json /tmp/ && python -m explorer.ingest --source cuad
ingest failed: .../data/cuad/CUADv1.json not found — run scripts/download_cuad.sh
exit=2

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
115 passed in 61.46s          # was 108
$ ruff format --check . && ruff check . && mypy backend/explorer --ignore-missing-imports
All checks passed! / Success: no issues found in 22 source files
```

`network_requests: 0` on the EDGAR step is the cache doing its job — a full re-ingest touches
sec.gov not at all.

### The AC that found a real defect: updated_at

"Bumps `updated_at` only on rows that actually changed" was failing on all four loaders.
Every upsert was an unconditional `DO UPDATE SET`, so a second identical run rewrote all
45,000 rows and moved `max(updated_at)` forward. Cube's `refresh_key` is `SELECT
MAX(updated_at)` (#14) — so every re-ingest would have invalidated every cached aggregate
while changing nothing. The fix is an `IS DISTINCT FROM` guard on each upsert (and on the
EDGAR `UPDATE`), with two tests: one asserting `max(updated_at)` is unchanged after a
no-op run, and one asserting a genuine edit *does* move it, so the guard cannot be tightened
into never noticing anything.

---

# CHECKPOINT after #11 — does the corpus support the product?

**Partly. Two of the three questions the product promises to answer are supported by real
data today; the third is not, and demo script 1 cannot run as written.**

Loaded, verified by querying the database after `make ingest`:

| table | rows |
|---|---|
| `folio_concepts` | 18,259 (+47,523 aliases) |
| `matters` | 152 |
| `deal_points` | 12,937 over 92 deal-point names |
| `clauses` | 13,823 over 41 clause types |
| `ingest_runs` | 54 |

### Supported

**"What was negotiated across them" — yes, strongly.** A real rollup, run against the loaded
data, over the fiduciary exception to the no-shop:

```
None                                                                    47
"Inconsistent" with fiduciary duties                                    44
"Reasonably likely/expected to be inconsistent" with fiduciary duties   35
Other specified standard                                                 9
```

n=135 of 152 for that deal point, 92 deal points available, and 96.2% of rows carry a source
span to drill into. This is the product's central claim and it works.

**"Where are we thick or thin" — yes.** The industry × year grid has genuinely populated cells
(Manufacturing 2021 n=34, Finance 2021 n=19, Information 2021 n=13) and genuinely thin ones,
which is what the Coverage tab exists to show.

### Not supported

**"Find comparables" as demo script 1 words it — no.** That script asks for *healthcare,
sponsor-side, $200M–1B, last five years*. Against this corpus:

- **healthcare → n=3.** Below any honest reporting threshold. Pharma and biotech, which a
  partner means by "healthcare", file under SIC 2834/2836 → Manufacturing (42 matters).
- **$200M–1B → no data at all.** `deal_size_band` is NULL for all 152 (#9, still open).
- **last five years → the corpus is 20 months**, 2020-03-13 to 2021-11-21.
- **sponsor-side → not a field we have.** Nothing in MAUD or EDGAR marks financial-sponsor
  buyers; it would have to be inferred from acquirer names.

So the demo script's filter chain returns nothing, and three of its four filters are
unbacked. **This is the finding, and it is a scoping problem, not a bug.** Options, none of
which I am choosing unilaterally:

1. **Rewrite demo script 1 against what the corpus has** — e.g. "Manufacturing, 2021, n=34"
   drilling into deal points. Honest, works today, less evocative than the healthcare pitch.
2. **Widen the industry crosswalk** so pharma/biotech route to Health Care, taking healthcare
   from 3 to roughly 20 (D22 would need revising, and the UI must say the definition is ours,
   not NAICS's).
3. **Populate deal value** (#9's open half) to restore the size axis, accepting an
   `is_inferred_deal_value` estimate with a published method.

Doing 2 and 3 makes script 1 approximately runnable. Doing neither means script 1 needs
rewriting. Either way the "last five years" phrasing has to go — the data is 20 months.

## Checkpoint decisions taken (post-#11)

Asked to keep going without pausing, so I took the three scoping calls the checkpoint
surfaced rather than leaving them open. Each is reversible and each is a config change.

**1. Life sciences are grouped with Health Care.** Added SIC 2833–2836, 3826, 3841, 3842,
3845 and 8731 rows to `data/mappings/sic_to_folio.csv`, each with a `basis` of
`PRODUCT DEFINITION - ... departs from NAICS`.

```
$ PYTHONPATH=backend python -m explorer.ingest --source edgar
$ # industry distribution, after
Health Care Industry                     25     (was 3)
Finance and Insurance Services           25
Manufacturing Industry                   22     (was 42)
Information Industry                     18
Real Estate, Rental and Leasing          12
Mining and Natural Resources             11
```

Cost accepted: this is **our** grouping, not NAICS's. NAICS and SIC both file pharma under
Manufacturing, and a reviewer who checks the crosswalk against NAICS will find a discrepancy.
That is why the departure is in the `basis` column of every affected row, in the file header,
in a test that pins it (`test_life_sciences_are_deliberately_grouped_with_health_care`), and
must appear in the UI wherever the dimension is shown. The alternative was an honest n=3 that
answers a question nobody asked.

**2. Demo script 1 drops the size filter.** `deal_value_usd` is NULL for all 152, so a size
facet renders as an empty rail. `docs/demo-scripts.md` now filters industry + year, and says
in the script itself to restore the size beat when #9 closes, not before.

**3. The corpus limits are written into the script, not just the worklog.** "Last five years"
is gone — the corpus is 20 months. "Sponsor-side" is documented as the partner's context, not
a filter the product offers, because no such flag exists in MAUD or EDGAR.

No test was weakened for any of this. `test_major_group_maps` was rewritten to assert meat
packing (SIC 2011) still maps to Manufacturing, so the crosswalk's default behaviour is still
pinned alongside the deliberate exception.

## #12 — Cube model for deal_points (LONG), numerator and denominator separate

`cube/model/deal_points.yml`. Six measures, seven dimensions, every one with a description
written for the model rather than for a human — `/meta` is all the agent sees when deciding
whether a measure answers the question (#24).

### Verification — a real rollup through the Cube REST API

```
$ curl -s -G 'http://localhost:4000/cubejs-api/v1/load' --data-urlencode 'query={
    "measures":["deal_points.n","deal_points.present_count"],
    "dimensions":["deal_points.position"],
    "filters":[{"member":"deal_points.deal_point_name","operator":"equals",
                "values":["Fiduciary exception:  Board determination standard-Answer (no-shop)"]}],
    "order":{"deal_points.n":"desc"}}'

  n= 47  present=  0  None
  n= 44  present= 44  "Inconsistent" with fiduciary duties
  n= 35  present= 35  "Reasonably likely/expected to be inconsistent" with fiduciary duties
  n=  9  present=  9  Other specified standard
  n=  7  present=  7  "Reasonably likely/expected violation" of fiduciary duties
  n=  5  present=  5  "Reasonably likely/expected breach" of fiduciary duties
  n=  2  present=  2  "Required to comply" with fiduciary duties
  n=  1  present=  1  "Violation" of fiduciary duties
  n=  1  present=  1  "Breach" of fiduciary duties

  refreshKeyValues: [[{"max":"2026-07-30T19:13:21.055"}]]     # refresh_key is live
```

That totals **n=151** and reads, in the product's own language: a fiduciary out appears in
**104 of 151** agreements, and the standard is "inconsistent with fiduciary duties" in 44 of
them. Numerator and denominator arrive as separate measures, so the UI can render "104 of 151"
and is never handed a pre-divided 68.9%.

```
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
128 passed in 65.61s          # was 115
$ ruff format --check . && ruff check . && mypy backend/explorer --ignore-missing-imports
All checks passed! / Success: no issues found in 22 source files
```

### The model is treated as an API

`test_cube_model.py` pins the properties that make it safe to point an LLM at:

- `deal_point_name` is a dimension, and **no measure is named after a deal point** — MAUD's
  93rd is rows, and this file does not change.
- the exact set of six measure names is asserted, with a message saying that changing it is an
  API change, because those names are the eval's label space (#27).
- **no `count_distinct_approx`** anywhere in the model directory, and every distinct count is
  exact.
- every public measure and dimension has a non-empty description, and the descriptions
  collectively say when *not* to use a measure.
- `refresh_key` is `MAX(updated_at)`, which is only safe because #11's ingest stopped touching
  unchanged rows.

The grep test failed first time on the file's **own header comment** telling the next author
never to use `count_distinct_approx`. Fixed by ignoring comment lines — a comment cannot
configure anything — rather than by softening the assertion or rewording the warning.

### `present_count` and its honest limit

The numerator counts positions other than an explicit absence (`None`, `No`, `N/A`). Its
description says plainly that MAUD records absence as the literal answer "None" for most deal
points but not all, so for a deal point whose answers are graded standards rather than
present/absent, the model should group by `position` instead. A numerator that silently means
the wrong thing on some deal points is exactly the "definition of the number" error the
project exists to close, so the caveat lives where the agent will read it.

### Not done

- No `matters` cube yet, so no industry/date dimensions and no join — that is #13, and the
  join to it is deliberately absent rather than stubbed.
- Medians are #15. There is no `type: avg` anywhere in this file and there will not be one.

## #13 — Cube model for matters: FOLIO hierarchy dimensions and facet counts

`cube/model/matters.yml` adds the `matters` and `folio_concepts` cubes plus a
`comparable_deals` view, and restores the `deal_points → matters` join that #12 deliberately
left out rather than stubbing against a cube that did not exist.

### The AC's open question, answered by testing rather than assuming

**Cube 1.7.15** (read from the running container, not from docs). A `hierarchies:` block was
added to the view; **the model compiled without error, but `/cubejs-api/v1/meta` returned
`"hierarchies": []` for every cube and view.** The key is accepted and not surfaced by the
REST API this product uses, so a native hierarchy would be dead configuration that reads as a
working feature. Removed, and the finding is recorded in the model's own header with the
version — a test asserts both survive in the file.

The product drills down on the denormalized `level_1_code`/`level_2_code`/`level_3_code`
columns written at ingest (#6).

### Facet counts, Cube vs hand-computed SQL

```
$ curl .../load?query={"measures":["comparable_deals.n"],"dimensions":["comparable_deals.label"]}
    25  Health Care Industry            |  $ psql: 25  Health Care Industry
    25  Finance and Insurance Services  |          25  Finance and Insurance Services
    22  Manufacturing Industry          |          22  Manufacturing Industry
    18  None                            |          (absent — inner join)
    18  Information Industry            |          18  Information Industry
    12  Real Estate, Rental and Leasing |          12  Real Estate, Rental and Leasing
```

Identical, with one deliberate difference: Cube returns an **18-row `None` bucket** the SQL
inner join dropped. Those are the matters with no industry, and the product must show them —
a coverage grid that silently omits what it cannot classify understates its own ignorance.
The test asserts the facet cells sum to **152**, which only holds because the unclassified
are visible.

### The join earning its place

```
$ # "fiduciary out, healthcare only" — one query across two cubes
  n= 12  None
  n=  9  "Inconsistent" with fiduciary duties
  n=  4  "Reasonably likely/expected to be inconsistent" with fiduciary duties
  total n = 25
```

A fiduciary out in **13 of 25** healthcare agreements. That is demo script 1's payload, served
by the semantic layer rather than by SQL in Python — and it needed the `deal_points → matters`
join, without which Cube reports `Can't find join path to join 'deal_points', 'folio_concepts'`.

```
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
136 passed in 61.84s          # was 128
$ ruff format --check . && ruff check . && mypy backend/explorer --ignore-missing-imports
All checks passed! / Success: no issues found in 22 source files
$ cd frontend && npx tsc --noEmit && npx vitest run
clean / 10 passed
```

### Deal-size bands: defined once, empty today

`deal_size_band` is a CASE in the model and nowhere else. A test greps `frontend/src` for
`$200M` and `200000000` and fails if either appears, so the UI cannot grow its own definition.
Every matter is currently `unknown` — `deal_value_usd` is NULL for all 152 (#9) — and the
dimension's description says `unknown` is a real value to be shown, not filtered away.

## #14 — refresh_key on updated_at: new rows appear without a restart

### The live test, measured

```
$ # query Cube, INSERT straight into Postgres, poll — nothing restarted
before n = 152 | refreshKeyValues [[{'max': '2026-07-30T19:12:07.801'}]]
after  n = 153 | observed staleness window: 11.3s
```

**New data appears in roughly 11 seconds without restarting anything.** That is Cube's default
10-second refresh-key check plus the query. It is not tuned and does not need to be: the whole
corpus reloads in 13 seconds. The figure is recorded in both model headers and a test asserts
it stays recorded, so nobody can quietly change the behaviour and leave the documentation
claiming the old number.

This only works because of #11: the ingest's `IS DISTINCT FROM` guards mean a no-op re-ingest
does not move `MAX(updated_at)`, so re-running `make ingest` does not invalidate every cached
aggregate for nothing.

### No pre-aggregations, on purpose

Stated in the model headers and asserted by a test that greps for `pre_aggregations`. At 152
matters and 12,937 deal points, Postgres answers these in milliseconds. A pre-aggregation
would add a build step, push the staleness window from seconds to minutes, and create a second
place for a number to be wrong — for no measurable gain. If a query is ever slow, measure it
first and put the evidence here.

### A flake, diagnosed rather than retried

The live test failed once in a full-suite run and passed standalone three times. Cause: the run
began seconds after `docker compose restart cube`, while Cube was still compiling the model and
answering 5xx — the polling helper treated that as "row not there yet" and burned the window.
Fixed by having the helper return `None` on a transient error and by waiting for Cube to become
queryable before taking the `before` reading. The assertion itself was not loosened: the row
must still appear.

```
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
140 passed in 75.96s          # was 136
```

## #15 — Medians via percentile_cont, and the mean that must never be used

### The corpus has no reverse termination fee to take a median of

The AC asks for the real median and mean **reverse termination fee**, side by side. MAUD does
not carry one. Its 92 questions are categorical or ordinal; the numbers that exist live inside
answer *text* — "4 business days", "within 12 months", "50%". There is no RTF magnitude in the
corpus at all, so there is no honest median to report for it. Reported instead: the deal points
that do carry numbers.

`numeric_value` is now populated at ingest by reading the number out of the expert's own answer
— normalisation, not extraction; nothing reads contract text. **809 of 12,937** rows carry one.
Answers that only *bound* a value ("Greater than 5 business days") store NULL: putting 5 there
turns an inequality into a data point that sits in a median looking like a measurement.

### The measured divergence, from the loaded corpus through Cube

```
$ curl .../load?query={"measures":["deal_points.numeric_n","deal_points.median_numeric_value",
    "deal_points.p25_numeric_value","deal_points.p75_numeric_value",
    "deal_points.mean_numeric_value_do_not_use_for_market"],
    "dimensions":["deal_points.deal_point_name"]}

  n= 150 median=12 p25=12 p75=12 mean=11.78  Tail Period Length-Answer
  n= 147 median= 4 p25= 4 p75= 4 mean= 4.01  Initial matching rights period (COR)-Answer
  n= 143 median= 2 p25= 2 p75= 3 mean= 2.54  Additional matching rights period for modifications (COR)
  n= 127 median= 4 p25= 4 p75= 5 mean= 4.07  Initial matching rights period (FTR)-Answer
  n= 121 median= 2 p25= 2 p75= 3 mean= 2.48  Additional matching rights period for modifications (FTR)
```

**Median 2.0 vs mean 2.54 business days**, n=143, for additional matching rights periods. A
partner told "about 2.5 business days is market" would be quoting the tail — no deal in the
corpus has a 2.5-day period; the market answer is 2, with a p75 of 3. That is the whole
argument for this issue, measured rather than asserted.

Tail Period is the mirror case: median 12 = p25 = p75, mean 11.78. A mean invents variation
where the market is uniform.

### Guardrails in the model

- `median_numeric_value`, `p25_numeric_value`, `p75_numeric_value` — all
  `PERCENTILE_CONT(x) WITHIN GROUP (ORDER BY numeric_value)`, asserted by test.
- exactly one `type: avg` exists and it is called
  **`mean_numeric_value_do_not_use_for_market`**, with "DO NOT use this" in its description. A
  test asserts it is the only average in the model and that it is named that way. An agent
  selecting measures by name cannot reach for it casually.
- `numeric_n` is a separate denominator, because the percentile's n (809) is not the deal
  point's n (12,937). Its description opens "THE DENOMINATOR FOR EVERY PERCENTILE BELOW".
- a skewed fixture `[2,2,2,2,2,3,3,4,40]` is checked both in Python and through Postgres'
  own `percentile_cont`: median 2.0, mean 6.67, and an assertion that if they ever match, the
  fixture stopped being skewed.

### A flaky test, fixed by understanding it rather than by widening it

#14's live refresh test failed twice under full-suite load and passed alone. First fix attempt:
assert with a query Cube had never run, on the theory that only cached *results* were stale.
That test failed immediately and taught the real mechanism — **a brand-new filtered query also
returns `[]` right after the INSERT, so it is the refresh-key value that is cached for ~10s,
not the query result.** The test is back to polling, with a 120s deadline to absorb suite load
and transient-error tolerance for a warming Cube.

It still failed — and fast, not on the deadline, which located the last cause: the *pre-check*
("this id is not in the corpus yet") was tripping on Cube's cached view of the **previous
run's** probe row, inserted and deleted seconds earlier. The probe id is now unique per run.
`158 passed` clean. The assertion never changed at any point: the row must appear without a
restart. Both findings are in the test's docstring where the next person to see a flake will
find them.

## #16 — Embedding cache: retrieval works with no API key

### The cache, measured

```
$ PYTHONPATH=backend python -m explorer.retrieval.warm_cache
{"step": "warm_cache", "texts_seen": 13975, "embedded_now": 13975, "entries_before": 0,
 "entries_after": 11797, "api_calls": 110, "file_bytes": 10008513, "duration_ms": 65297.0}

$ du -h data/embeddings/vectors.npz
9.5M

$ # then, with the key removed entirely
$ env -u OPENAI_API_KEY python -c "...EmbeddingCache(api_key=None)..."
entries: 11797 | file MB: 10.01
hit with no key -> vector dim (256,) dtype float16 | api_calls 0
miss without key -> 1 text(s) are not in the embedding cache (11797 cached at vectors.npz)
                    and OPENAI_API_KEY is not set. Run `python -m explorer.retrieval.warm_cache`...
```

**13,975 texts in, 11,797 vectors out.** The 2,178-entry gap is content addressing doing its
job: that many clause texts are byte-identical to another clause somewhere in CUAD (boilerplate
governing-law and assignment provisions repeat across contracts), and a content-keyed cache
stores each exactly once. A cache keyed on clause id would have paid to embed all 13,975.

110 API calls at batch size 128. 9.5 MB committed, which is why the vectors are 256-dimensional
`float16` rather than the model's native 1536-dimensional `float32` — that would have been a
~86 MB file in a public repo. #17's ablation measures what, if anything, the shortening costs.

### The three cases, each with a test that runs with no key

| case | behaviour |
|---|---|
| hit | vector returned, `api_calls == 0`, no key needed |
| miss **with** a key | embedded once, kept in memory, second request does not re-embed |
| miss **without** a key | `EmbeddingUnavailable` naming the cached count and the fixing command |

The miss-with-key test stubs the client, so no test needs a key or a network — including the
one that proves an API call happens exactly once.

### The committed file is never written by a query path

`save()` is called only by `warm_cache`. A test asserts that embedding a new text with a key
in hand leaves the file byte-identical. Otherwise a developer with a key would silently
rewrite a version-controlled artefact just by running a search, and the diff would appear from
nowhere.

```
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
166 passed in 73.80s          # was 158
```

## #17 — Hybrid retrieval with a real ablation

### The ablation, run with no API key

```
$ env -u OPENAI_API_KEY python -m explorer.evals.retrieval_ablation
{"eval": "retrieval_ablation", "queries": 90, "corpus": 152, "duration_ms": 1889.1,
 "best": "hybrid alpha=0.5"}

| method            | recall@1 | recall@5 | recall@10 |  MRR  |
|-------------------|----------|----------|-----------|-------|
| pure BM25         |  0.711   |  0.822   |   0.911   | 0.769 |
| hybrid alpha=0.3  |  0.722   |  0.856   |   0.911   | 0.775 |
| hybrid alpha=0.5  |  0.744   |  0.856   |   0.900   | 0.785 |
| hybrid alpha=0.7  |  0.733   |  0.833   |   0.889   | 0.767 |
| pure vector       |  0.722   |  0.778   |   0.811   | 0.744 |
```

**Hybrid wins, narrowly** — 0.785 at alpha=0.5 against 0.769 BM25 and 0.744 vector. Alpha was
not tuned toward a result; the sweep is fixed at 0.0/0.3/0.5/0.7/1.0 and the table is whatever
it produced.

### The caveat that matters more than the headline

Two of the three query phrasings are **saturated** — every method scores 1.000 recall@1:

```
| phrasing      | method      | recall@1 | recall@5 | recall@10 |  MRR  |
| industry_year | pure BM25   |  0.133   |  0.467   |   0.733   | 0.306 |
| industry_year | hybrid 0.5  |  0.233   |  0.567   |   0.700   | 0.355 |
| industry_year | pure vector |  0.167   |  0.333   |   0.433   | 0.231 |
| paraphrase    | (all three) |  1.000   |  1.000   |   1.000   | 1.000 |
| parties       | (all three) |  1.000   |  1.000   |   1.000   | 1.000 |
```

`parties` and `paraphrase` both name the acquirer, and the indexed summary contains that name
verbatim — no retriever can fail. So the aggregate MRR is dominated by a task nothing can lose,
and **the only discriminating row is `industry_year`**: hybrid 0.355, BM25 0.306, vector 0.231.
The results file says this in its own section rather than letting the 0.785 stand unqualified,
and the saturation notice is generated from the data, so it appears automatically if a future
eval set is too easy.

Note what that row also shows: on the one hard slice, **pure vector is the worst of the three**
— 256-dimensional embeddings of a one-line summary lose to lexical matching on a query like
"Health Care Industry merger agreement signed in 2021". Hybrid beats both, which is the case
for keeping it, but the honest reading is "BM25 is doing most of the work here".

### The eval set is ground truth, not authored judgements

Hand-authoring "query -> relevant matters" would mean scoring a retriever against my own
guesses. Instead each query describes exactly one matter using fields already in the database,
and the single relevant result is that matter — known-item retrieval, reproducible by anyone,
unnudgeable. The sample is every nth qualifying matter, so it cannot be reshuffled until the
numbers improve. What it does **not** measure is topical similarity ("deals like this one"),
which needs judgements this corpus does not carry; that limitation is stated in the results
file, and #18's comparable ranking is not covered by this table.

### Normalization is the correctness story

BM25 scores are unbounded and query-dependent; cosine sits in ~[0,1]. Blending raw means BM25's
scale swamps the vector term and `alpha` silently stops meaning anything — the results still
look plausibly ordered. Both sides are min-max normalized per query, and three tests hold it:
component scores stay within [0,1], a flat distribution maps to zeros rather than NaN, and
moving alpha from 0 to 1 actually flips the top result on a query where the two methods
disagree.

`alpha` is `HYBRID_ALPHA` from the environment with a per-query override, never a literal.

```
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
177 passed in 84.32s          # was 166
```

## #18 — POST /comparables: FOLIO filter, then hybrid rank

### Verification against the running stack

```
$ docker compose up -d --build api
$ curl -s -X POST localhost:8000/comparables -H 'content-type: application/json' \
    -d '{"folio_industry_code":"RCSG4k3ah1Pu5YgPexPgOmL","limit":3}'

candidates 25 returned 3
applied: {'folio_industry_code': 'RCSG4k3ah1Pu5YgPexPgOmL',
          'folio_industry_label': 'Health Care Industry',
          'rolled_up_to_descendants': 91, 'deal_size_band': None,
          'ranked_by': 'matter id (no description given)'}
  contract_1   | ACCELERON PHARMA INC.       | Health Care Industry | inferred True
  contract_104 | PPD, INC.                   | Health Care Industry | inferred True
  contract_105 | PRA HEALTH SCIENCES, INC.   | Health Care Industry | inferred True

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
188 passed in 87.25s          # was 177
```

That is demo script 1's first beat working end to end against real data — and note
`rolled_up_to_descendants: 91`, the FOLIO hierarchy doing its job: filtering on Health Care
matched the concept plus its 91 descendants via the denormalized level columns.

### Filter before rank, not after

Ranking the corpus and dropping out-of-filter results afterwards is the obvious version and it
is wrong twice: a request for ten healthcare comparables returns three because seven of the
top ten were filtered away, and the scores that survive were normalized against a corpus the
user never asked about. Here the filter runs in Postgres and the hybrid index is built over
exactly the surviving matters, so relevance is relative to the requested slice. Asserted by a
test that ranks a health-care-filtered request and requires every result to still be health
care.

### An unknown FOLIO code is a 400, not an empty list

The nastiest failure mode in the design: zero results and a bad filter value look identical to
a reader. A code that resolves to nothing raises rather than returning `[]`.

### Two things the tests taught

**`AmbiguousParameter`.** `%(industry)s IS NULL` gives Postgres no way to infer a parameter
type and the endpoint 500'd. Fixed with explicit `::text` / `::date` casts — every filter is
still a bound parameter, never interpolated.

**The 503 was correct and my test was wrong.** Ranking free text needs that text embedded, so
with no key only *cached* queries can be ranked. My first tests used ad-hoc descriptions and
got 503s. That is the designed contract from #16, not a limitation to work around: the no-key
tests now use a query `warm_cache` embedded, and a separate test asserts an uncached query with
no key returns 503 naming the cached count and the fixing command — never a silent API call,
never a bare 500.

### Not done

- `deal_size_band` is accepted and only matches `'unknown'`, because that is the only value any
  matter has (#9). It is wired so it works the day values land, and it cannot silently match
  everything in the meantime.

## #19 — Explore tab: faceted search with live counts from Cube

Picked this up mid-flight: the view, rail, card and `/facets` endpoint were already written but
uncommitted, with two gate failures, one failing spec, no backend test for `facets.py` at all,
and a correctness bug in how the tab filtered. All four are dealt with below.

### The facet rail against real data

```
$ docker compose up -d --build && curl -s localhost:8000/healthz
{"status":"ok","db":"ok","cube":"ok","version":"0.1.0"}

$ curl -s -X POST localhost:8000/facets -H 'content-type: application/json' -d '{}'
total_n=152  unfiltered_n=152

[industry] Industry  total_n=152
   Finance and Insurance Services Industry    n=25   code=RCksXAlY9lRN16wERqZZ8Tk
   Health Care Industry                       n=25   code=RCSG4k3ah1Pu5YgPexPgOmL
   Manufacturing Industry                     n=22   code=RBOjgvcq6Z33XxMhTxWiiDS
   unclassified                               n=18   code=None
   Information Industry                       n=18   code=RHwCmZ2yKrJobzC86GC6Ep
   Real Estate, Rental and Leasing Industry   n=12   code=RjKL1UdfWL1FCPVhnbIFSF

[year] Signing year  total_n=152
   2021  n=111    2020  n=38    unclassified  n=3

[band] Deal size  total_n=152
  UNAVAILABLE: Deal size is not filterable: no deal values have been enriched yet, so all 152
               matters sit in one bucket. Tracked as issue #9.
   unknown                                    n=152  code=None
```

111 + 38 = 149, which is exactly the enriched `signing_date` count from #9; the remaining 3
are `unclassified` rather than dropped. Health Care is 25 under the D30 grouping.

### A facet group must not filter itself

Selecting Health Care and re-reading the rail:

```
$ curl -s -X POST localhost:8000/facets -d '{"folio_industry_label":"Health Care Industry"}'
total_n=25 of unfiltered_n=152
industry group still offers 15 values (must NOT collapse to 1):
   Finance and Insurance Services Industry    n=25   selected=False
   Health Care Industry                       n=25   selected=True
   Manufacturing Industry                     n=22   selected=False
year, now narrowed by the industry filter:
   2021  n=19    2020  n=5    unclassified  n=1
```

The industry group keeps all 15 values so the partner can switch; every *other* group narrows.
19 + 5 + 1 = 25 = `total_n`, so the groups agree with each other and with the header.

### The bug that mattered: Explore filtered in the browser

The tab held the industry **label**, but `/comparables` filters by FOLIO **code**, so the label
had nowhere to go. The uncommitted code compensated by filtering `results.matters` client-side.
Measured against the running stack, that is what the partner would have seen:

```
$ curl -s -X POST localhost:8000/comparables -d '{"limit":25}'      # the old request shape
candidate_count reported to the partner : 152
rows the browser would have kept        : 6 of 25
```

**Six healthcare deals shown, under a header reading "showing 6 of 152", when the corpus holds
25.** Two independent failures: the denominator counted matters nobody asked about, and the
hybrid scores were normalized over the whole corpus — the exact property #18 was built to
guarantee, undone one layer up.

Fixed at the root rather than in the view. `comparable_deals.code` is now public in the Cube
view, `/facets` groups it alongside the label, and the rail hands the code to `/comparables`:

```
$ curl -s -X POST localhost:8000/comparables \
    -d '{"folio_industry_code":"RCSG4k3ah1Pu5YgPexPgOmL","limit":25}'
candidate_count=25  returned_count=25
industries present in the ranked list: {'Health Care Industry'}
applied: {"folio_industry_code": "RCSG4k3ah1Pu5YgPexPgOmL",
          "folio_industry_label": "Health Care Industry",
          "rolled_up_to_descendants": 91, ...}
```

25 = the facet count, all 25 in-slice, ranked within the slice. The client-side filter is gone.

Passing the code rather than the label also pre-empts #25 on this path: there is no label to
mis-resolve, so "Health Care" vs "Healthcare" cannot arise from a facet click at all. `code` is
`None` for the `unclassified` bucket — a real bucket with no concept behind it, and a fabricated
code there would return nothing while looking like a filter.

### Deal size ships disabled, with the reason

`deal_value_usd` is NULL on all 152 (D25, #9 open). The group renders with its single `unknown`
value, disabled, carrying the sentence above. Hiding it would claim the corpus has no size axis;
enabling it would offer a filter that cannot narrow anything. The reason is emitted only when a
group has no informative value, so it disappears on its own when #9 lands — pinned by a test
asserting industry and year carry no reason.

### A dead Cube is not an empty result

```
$ docker compose stop cube
$ curl -s -X POST localhost:8000/facets -d '{}'
HTTP 503
{"error":{"code":"unavailable","message":"The semantic layer (Cube) did not answer. Facet
 counts and deal-term rollups come from it, so this is reported rather than shown as zero
 results.","detail":null}}
```

The UI renders that as "Counts unavailable" under `role="alert"`, visually distinct from the
empty state, and a spec asserts the empty-state copy is *absent* when the error state shows.

Cube's long-poll cost a live 503 on the first facet request: it answers 200 with
`{"error": "Continue wait"}` and expects the same request re-issued. Reading any body with
"error" in it as failure — the obvious reading — turns every cold-start query into a 503.
`cube_client.py` retries up to 10 times and is the single place the API talks to Cube, so the
logging contract holds:

```
  event: cube_query   request_id: 8412f45293f4
  measures: ['comparable_deals.n']   row_count: 1   duration_ms: 8.5
```

### `facets.py` had no test, and passing proved nothing

It was written ahead of its test — a TDD deviation in the work I inherited, recorded here rather
than papered over. Writing 16 specs after the fact does not establish they bite, so each of the
three load-bearing claims was mutation-checked:

| mutation | result |
|---|---|
| `_filters(exclude=key)` → `exclude=""` (let each group filter itself) | `TestSelfFiltering::test_the_industry_group_is_not_filtered_by_the_selected_industry` failed, 10 passed |
| drop zero-count rows from `values` | `TestZeroCounts::test_a_zero_count_value_is_returned_not_dropped` failed, 10 passed |
| send `signing_year` as an int | `TestYearIsComparedAsAString::test_an_int_year_reaches_cube_as_a_string` failed, 10 passed |

Each mutation killed exactly its own test and nothing else. Cube is stubbed in these, so they
run in the no-key gate with no container up; the live checks are the curl output above.

### Two defects in the inherited work

**`signing_year and str(signing_year)` types as `Literal[0] | str | None`** — it returns `0`,
not `None`, for a falsy year. mypy caught it. The class of bug matters more than year 0 ever
will: a falsy-but-present filter silently dropping is how rails come back empty.

**`signing_year` is a string dimension now**, `to_char(signing_date, 'YYYY')`, because Cube's
`equals` does not coerce across types — an int 2021 against a string dimension matches nothing
and returns an empty rail that reads as "no 2021 deals". The request still accepts an int.

### The failing spec was the spec's fault

`Explore.test.tsx`'s "does not steal keys while typing" awaited `findByLabelText('describe the
deal')`, which resolves on first render because the search input sits outside the loading
branch — so the following `getByTestId` ran before any card existed. The guard it was actually
testing is correct. It now awaits the list first and additionally asserts the cursor did *not*
move to the second card. Diagnosed before changing anything, per the rule; the implementation
was never at fault.

### Gates

```
$ ruff format --check . && ruff check .
47 files already formatted
All checks passed!

$ mypy backend/explorer --ignore-missing-imports
Success: no issues found in 30 source files

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
204 passed in 78.32s          # was 188 at #18

$ cd frontend && npx tsc --noEmit && npx vitest run && npm run build
Tests  25 passed (25)         # was 21 passed, 1 failed
✓ built in 293ms
```

### Not done

- **Expandable FOLIO hierarchy in the rail — not built, because this corpus has no hierarchy
  to expand.** Measured before deciding:

  ```
  $ curl -sG localhost:4000/cubejs-api/v1/load --data-urlencode 'query={"measures":
      ["comparable_deals.n"],"dimensions":["comparable_deals.level_1_code",
      "comparable_deals.level_2_code","comparable_deals.level_3_code"]}'
  distinct level_1: 2      # one real code + None for the 18 unclassified
  distinct level_2: 2      # same
  distinct level_3: 15
  ```

  Every classified matter shares the same level-1 and level-2 parent
  (`R8f4qGdjxuiQary8OBpq8W9` → `RDIwFaFcH4KY0gwEY0QlMTp`, "Industry"). All branching is at
  level 3, and those 15 values are exactly what the rail already lists. A tree here renders one
  root containing all 15 leaves: an extra click that reveals nothing and implies a structure the
  data does not have. Left flat deliberately.

  This does not affect filtering, which rolls up correctly through the denormalized level
  columns — a Health Care selection still matches `rolled_up_to_descendants: 91`. The AC is
  unmet on the *interaction*; the capability behind it works. It becomes worth building if a
  corpus arrives with matters at more than one level-2 industry.
- **Transaction type facet.** Named in the AC; no such field exists in MAUD or EDGAR, so there
  is nothing to count. Same category as "sponsor-side" from the #11 checkpoint.
- **`?` shortcut overlay** is the shell's (#5); `f` and `Esc` are wired here and covered by
  specs, `j`/`k`/`Enter` likewise.
- Docker's daemon was wedged at the start of this session (socket accepting connections but
  never answering `/_ping`); it needed a hard restart before any of the live verification above
  could run.

## #20 — Matter card with drill-through and a copyable summary

`GET /matters/{id}` behind a card that expands into the deal points for that matter, each with
the clause text behind it. Deliberately **not** through Cube: the semantic layer's footprint is
facet counts, rollups and the coverage grid, and individual record fetch is outside it.

### The clause text is the file, not a description of it

```
$ curl -s localhost:8000/matters/contract_1
target       : ACCELERON PHARMA INC.
acquirer     : MERCK SHARP & DOHME CORP.
industry     : Health Care Industry | inferred: True
deal value   : None
source       : maud/data/contracts/contract_1.txt
deal points  : 89 | located: 80

--- drill-through: "Ability to consummate" concept is subject to MAE carveouts => No
    span [234875, 239289)
    text: '“Company Material Adverse Effect” means any change, effect, event, inaccuracy,
            occurrence, or other matter that would reasonably be expected to have, '
```

Checked against the downloaded file rather than trusted:

```
$ python3 - <<'PY'
raw = open('data/maud/data/contracts/contract_1.txt').read()
print(dp['clause_text'] == raw[dp['source_span_start']:dp['source_span_end']])
PY
byte-exact against the downloaded file: True
len: 4414
```

A pinning test asserts the same equality, so a future refactor that starts summarising or
re-wrapping the excerpt fails the suite rather than quietly changing what the card claims.

### Nothing is invented when the span is missing

9 of this matter's 89 deal points have no located range (495 of 12,937 corpus-wide). Those
return `clause_text: null` with a reason — `MAUD located no character range for this label in
the source agreement.` — and the card renders the sentence. An empty box reads as "there is no
such clause"; the truth is "MAUD located no range for it", and those are different claims.

Three distinct reasons, so the card never has to guess: no span recorded, source file absent
(the corpus is gitignored, so this is normal on a fresh checkout), or a range that falls outside
the file. `located_count` and `deal_point_count` both ship, so the card can say **80 of 89**
rather than a bare percentage.

### The summary is built server-side, because it leaves the app

Pasted into a deck, the paragraph loses every visual cue the UI used to qualify it. So the
inferred badge becomes the literal word and the denominator is written out:

```
MERCK SHARP & DOHME CORP. / ACCELERON PHARMA INC. — Health Care Industry (inferred from SIC,
not an expert label), signed 2021-09-29. deal value not available. Negotiated terms (n=89, 80
traced to a source span): ... Source: ACCELERON PHARMA INC. - Agreement and Plan of Merger
(maud/data/contracts/contract_1.txt). Deal-point labels are MAUD expert annotations (CC BY 4.0).
```

"deal value not available" rather than a blank or a zero — #9 is open and D25 refused to
estimate it. Tests assert the citation, the word "inferred", `n=89`, and that no markup can
reach the clipboard.

### An unknown id is a 404 that says so

```
$ curl -s localhost:8000/matters/nope
HTTP 404
{"error":{"code":"not_found","message":"No matter 'nope'. This is not an empty result — the id
 does not exist.","detail":null}}
```

### Two defects found while building

**A crash that would have taken the whole result list down.** The card called
`detail.deal_points.map` on whatever the fetch returned. A 200 whose body is not a matter detail
— a misrouted proxy, a stale service worker — threw `Cannot read properties of undefined` inside
React and blanked the list, not just the card. Surfaced because Explore's test mock answers every
non-facets URL with the comparables body, which is exactly that shape. The response is now
checked for a `deal_points` array and reported as an error state instead.

**A regression I introduced.** Rewriting the expanded panel dropped the hybrid/vector/bm25 score
breakdown that #19 showed. `Explore.test.tsx`'s "Enter expands the focused result" caught it. The
breakdown is back, alongside the drill-through: the ranking should be as inspectable as the
clauses are.

### Path resolution, and the one place a DB value becomes a file read

`matters.source_file` is recorded relative to `data/` (`maud/data/contracts/contract_1.txt`),
not the repo root — the first implementation joined it to the repo root and every card came back
with `source_text_available: false`. Resolved against `DATA_ROOT`, and the resolved path is
required to stay inside it: the value comes from our own ingest rather than a request, but this
is the only place a database string turns into a filesystem read.

Contract texts are ~700 KB and every deal point on a card cites the same one, so the file is read
once per card and memoised across requests (bounded at 8 files) instead of 89 times.

### Gates

```
$ ruff format --check . && ruff check .
49 files already formatted
All checks passed!

$ mypy backend/explorer --ignore-missing-imports
Success: no issues found in 31 source files

$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
217 passed in 76.76s          # was 204 at #19

$ cd frontend && npx tsc --noEmit && npx vitest run && npm run build
Tests  35 passed (35)         # was 25
✓ built in 301ms

$ curl -s -o /dev/null -w '%{http_code}' localhost:5173/api/matters/contract_1
200                            # through the nginx proxy, not just the API directly
```

### Not done

- **"Top" negotiated terms in the pasted paragraph are the first five alphabetically**, not the
  five that matter. Nothing in MAUD ranks deal points by salience, and inventing an order
  (preferring non-"No" positions, say) would be a judgement presented as data. It reads oddly —
  the paragraph opens on `"Ability to consummate" concept is subject to MAE carveouts` — and it
  is honest. A defensible ordering exists (frequency of the deal point across the corpus, which
  is derivable) and belongs with the rollup work in #21.
- **Transaction type on the card**: no such field exists in MAUD or EDGAR, same as #19.
- **Deal value on the card** renders "not available" until #9 lands.

## #21 — Deal Terms: the rollup over a selected set

The view that replaces the comparison chart an associate builds by hand. `POST /deal-terms`
takes the matter ids Explore is showing and returns one row per deal point; every number comes
from Cube, so the figure here and the facet count in the rail cannot mean different things.

### The request/response pair the AC asked for

```
$ curl -s -X POST localhost:8000/deal-terms -H 'content-type: application/json' \
    -d '{"matter_ids":["contract_1", ... ,"contract_8"]}'

selection_n           : 8
percentage_threshold  : 30
answered deal points  : 92
absent  deal points   : 0
total rows            : 92

rows rendered as a percentage: 0          # at n=8, by rule

deal point                                                     display   positions
Definition includes stock deals-Answer                         8 of 8    Greater than 50% but not "all…
Knowledge Definition limited to one or more identified persons 8 of 8    Yes=8
Knowledge Definition-Answer                                    8 of 8    Constructive knowledge=6, Actual knowledge=2
Limitations on FTR Exercise-Answer                             8 of 8    Material breach of no-shop…

numeric deal points: 7
  Initial matching rights period (FTR)-Answer   median=4.0 p25=3.5 p75=4.0 n=7
  Definition includes stock deals-Answer        median=50.0 p25=50.0 p75=50.0 n=4
```

### The rendering rule, verified at its edge on real data

The rule is per **row**, not per selection — the denominator that matters is how many of the
selected matters actually answer that deal point. Asked for 40 matters:

```
selection_n: 40 | threshold: 30
percentage rows: 85 | count rows: 7

Change in law (Y/N)                                  100%      answered_n=40
Buyer consent requirement (ordinary course)-Answer   100%      answered_n=40
--- still counts, because answered_n < 30 ---
Additional matching rights period for modifications  29 of 29  answered_n=29
Breach of No Shop required to be willful, material…  21 of 21  answered_n=21
```

`answered_n=29` renders `29 of 29` while `answered_n=40` renders `100%`, in the same response.
A selection-level switch would have called both a percentage and quietly overstated the second.
Three tests pin the boundary — at the threshold, one below it, and that no row anywhere in a
small selection carries a `%`.

The rule lives in one function server-side and the pre-rendered string is what ships. The view
never divides two numbers; if a `/` appears in `DealTerms.tsx`, the rule has already been broken.

### Absence is a row, verified

A one-matter selection is the case where absence actually shows up:

```
$ curl -s -X POST localhost:8000/deal-terms -d '{"matter_ids":["contract_1"]}'
answered: 89 | absent: 3 | rows: 92

Breach of Meeting Covenant required to be willful, materia…  0 of 1
Breach of No Shop required to be willful, material and/or…   0 of 1
COR standard (board determination only)-answer               0 of 1
```

92 rows either way. The vocabulary is read from Cube rather than hardcoded, so a 93rd deal point
appears here as a row the day it lands (D8) with no code change.

Two different zeroes, deliberately distinguished: `answered_n = 0` means no selected matter has
a labelled answer, while `present_count = 0` with `answered_n = 8` means all eight were asked and
all eight said no. Both render `0 of 8`; only the first carries the explanatory sentence.

### Drill-through

```
$ curl -s -X POST localhost:8000/deal-terms/drill \
    -d '{"matter_ids":[...8...],"deal_point_name":"Knowledge Definition-Answer"}'
contract_1     Constructive knowledge
contract_3     Actual knowledge
contract_5     Actual knowledge
...
```

Clause text deliberately stays with `GET /matters/{id}` (#20) — one place reads a byte range out
of a source agreement, and it is not this endpoint.

### An empty selection is a 422

```
$ curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8000/deal-terms -d '{"matter_ids":[]}'
422
```

An unfiltered rollup would answer confidently about all 152 matters while looking exactly like
an answer about the eight the partner chose. The view refuses too, and does not fetch at all
with an empty selection.

### Scope is on the response, not in UI copy

`scope_note` ships with the numbers: *"These are comparable PUBLIC deals from the MAUD study of
SEC-filed merger agreements. This is not this firm's own matter history and must not be
described as it."* On the response rather than in the component so it travels into anything that
renders these figures.

### Positions, not just present/absent

`present_count` counts answers that are not `None`/`No`/`N/A`, which is right for present/absent
deal points and wrong for graded ones — `Knowledge Definition-Answer` is `Constructive
knowledge=6, Actual knowledge=2`, and "8 of 8 present" says nothing useful about it. Every row
therefore carries its full position distribution, and the view renders it beneath the headline.

### Gates

```
$ ruff format --check . && ruff check .          All checks passed!
$ mypy backend/explorer --ignore-missing-imports Success: no issues found in 32 source files
$ env -u OPENAI_API_KEY pytest backend/tests -q -m "not needs_key"
235 passed in 80.99s          # was 217 at #20
$ cd frontend && npx tsc --noEmit && npx vitest run && npm run build
Tests  44 passed (44)         # was 35
✓ built in 339ms
```

### Not done

- **The selection is the matters Explore currently lists, not a hand-picked subset.** There is
  no per-card checkbox yet, so "the selected set" means "the current result set" (capped at the
  25 Explore requests). Narrowing by facet is the way to change it. A real multi-select belongs
  with the Coverage cross-filter work.
- **No refusal on a thin selection.** A one-matter rollup answers `0 of 1` and `1 of 1` today.
  That is #23's `min_n` gate, which is also the k-anonymity control, and it is deliberately not
  pre-empted here.
- Deal-point ordering is by prevalence then alphabetical for absent rows; no salience ranking
  exists in MAUD, same limitation recorded under #20.

## #21 follow-up — the drill-through did not drill through

Checked the built views against `docs/demo-scripts.md`, which CLAUDE.md names as the acceptance
test for the product. Three gaps; the first was a closed AC that had been redefined rather than
met.

**Script 2 beat 5 — "the actual clause language from the deals that have it, with source file
and character offsets".** `/deal-terms/drill` returned `matter_id` and `position` only. That is
a list of pointers: the associate this view replaces would still have to open eight agreements.
I had justified it in the #21 commit as "clause text stays with `/matters/{id}`", which is an
architectural preference standing in for an unmet acceptance criterion.

Now returns the language itself, reading Postgres rather than Cube — record fetch and source
spans are outside Cube's footprint by design, and routing document text through the aggregate
layer would be worse:

```
$ curl -s -X POST localhost:8000/deal-terms/drill \
    -d '{"matter_ids":[...8...],"deal_point_name":"Knowledge Definition-Answer"}'

contract_1 (ACCELERON PHARMA INC.) -> Constructive knowledge
maud/data/contracts/contract_1.txt [255704, 256033)
“Knowledge” of Parent or the Company, as applicable means the actual knowledge of the
individuals set forth on Schedule 9.3 after making reasonable inquiry of…

contract_3 (AEGION CORPORATION) -> Actual knowledge
maud/data/contracts/contract_3.txt [20271, 20434)
“Knowledge of the Company” means the actual knowledge of the individuals identified on
Section 1.01(a) of the Company Disclosure Schedule…
```

That pair is the product working: contract_3 says *actual knowledge of the individuals
identified*; contract_1 says *actual knowledge … after making reasonable inquiry*, which is why
MAUD labels one Actual and the other Constructive. A partner can now see the distinction rather
than take the label on trust.

`slice_source` is shared with #20 rather than reimplemented — two implementations would
eventually disagree about what "no text" means, invisibly.

**Script 1 beat 1 — corpus counts before any interaction.** `/facets` now returns them:

```
corpus: {'matters': 152, 'deal_points': 12937, 'industries': 14}
```

14, not 15: `unclassified` is a bucket rather than an industry, and an industry with n=0 is not
one the corpus covers. A test pins both exclusions.

**A crash of the same class as #20's.** `facets.corpus.matters` threw on a payload without
`corpus`, taking Explore down. Guarded. That is twice now that an unexpected 200 body has
blanked a view — worth watching for in the remaining views.

### Not done

- **Script 1 beat 4, headline terms on the collapsed card.** Still needs a salience order that
  MAUD does not carry, the same limitation recorded under #20. Deal-point frequency across the
  corpus is derivable and would be defensible; it is not built.

### Gates

```
ruff + mypy                                     clean
env -u OPENAI_API_KEY pytest backend/tests -q   239 passed        # was 235
frontend: tsc + vitest + build                  47 passed         # was 44
```

## #22 — Coverage: FOLIO x period, thin cells loud not faded

```
$ curl -s -X POST localhost:8000/coverage -d '{}'
rows: 15  columns: 2020, 2021, unclassified  min_n: 5
total: 152  thin: 33 of 45  empty: 16

Finance and Insurance Services Industry   2020=6   2021=19  total=25
Manufacturing Industry                    2020=4*  2021=18  total=22   (* below min_n)
Construction Industry                     2020=0*  2021=3*  total=3
```

Only 12 of 45 cells are reportable. Column axis is `signing_year`, not deal size: #22 specifies
size, but `deal_value_usd` is NULL on all 152 matters (#9) so that grid is one column wide.
`column` accepts `band` too — offered, not silently substituted — and both axes carry a
`column_note` explaining themselves.

**Thinness is data, not styling.** Every cell carries `reportable` and, when false, a `note`
naming the actual n and the threshold. The view marks it with a distinct warm background and
bold weight rather than fading it — default BI dims small numbers, which reads as "small"; this
reads as "not reportable," the opposite signal on purpose. A test asserts the marker class is
present at n<min_n and absent at n=min_n exactly.

Clicking a cell hands Explore the FOLIO **code** behind the row, never the label (#25's failure
mode), plus the column year — verified with a click test against a mocked `onNavigateToExplore`.

`min_n=5` lives in `Settings` alongside `percentage_threshold`; #23's refusal reads the same
value, so a KM user sees a cell is thin before ever hitting the gate that enforces it.

Gates: ruff/mypy clean, `env -u OPENAI_API_KEY pytest` 254 passed (was 239), frontend 59 passed
(was 47), build clean. Verified through the nginx proxy at localhost:5173, not just curl to 8000.

## #23 — min_n refusal: the single most important behavior in the product

**The gap this closes.** Before this issue, a selection of n=1 rendered `"1 of 1"` in the
existing count-vs-percentage rule — literally naming whether one specific client's deal has a
given provision. That is the exact k-anonymity failure CLAUDE.md names: an analyst filtering
until n=1 has extracted one client's negotiated term through the aggregate layer, around the
ethical wall, without ever opening a document. `min_n` did not exist as a gate until now.

**Server-side, both endpoints, before any query runs.**

```
$ curl -s -X POST localhost:8000/deal-terms -d '{"matter_ids":["contract_1","contract_2","contract_3"]}'
{"selection_n": 3, "refused": true,
 "refusal": {"reason": "insufficient_n", "n": 3, "threshold": 5,
             "message": "n=3 — insufficient to characterize (threshold 5)"}, "rows": []}

$ curl -s -X POST localhost:8000/deal-terms/drill \
    -d '{"matter_ids":["contract_1","contract_2","contract_3"],"deal_point_name":"Ticking fee"}'
{"matters": [], "refused": true, "refusal": {..., "n": 3, "threshold": 5}}
```

Drill-through is the sharper of the two: it returns a named matter's actual clause text, so if
the rollup refused at n=3 but drill did not, the gate would be decorative — nothing would stop
clicking straight through to the individual clauses of the matters the rollup declined to
characterize. Both refuse from the same `_refusal()` check.

**No bypass via the request body.**

```
$ curl -s -X POST localhost:8000/deal-terms -d '{"matter_ids":["contract_1"],"admin":true,"bypass_min_n":true}'
refused: True | n=1 — insufficient to characterize (threshold 5)
```

There is no flag that turns it off because none is read. A test proves the refusal happens
*before* any Cube query or database read: `cube.payloads == []` on a refused rollup, and a
monkeypatched `_run_drill_query` that is never called on a refused drill.

**The 8-matter demo path is unaffected.**

```
$ curl -s -X POST localhost:8000/deal-terms -d '{"matter_ids":[...8...]}'
refused: False | rows: 92
```

**The second gate — extraction confidence — is built and tested but currently inert, on
purpose.** MAUD's own labels are gold and are never gated by this (CLAUDE.md: do not re-extract
what lawyers already labelled); it exists for extractor output. No extractor has run the #28
calibration pass yet, so `confidence_lookup()` returns `None` for every deal point today —
fabricating a plausible accuracy number to make the gate "do something" would violate the
no-fabricated-numbers rule. The mechanism is proven with an injected confidence source in tests
(`monkeypatch.setattr(module, "confidence_lookup", lambda name: 0.3)` → row excluded,
`display_kind: "low_confidence"`, distinct `gate_note`), and becomes live the day #28 publishes
real per-deal-point accuracy.

**The refusal is its own response shape**, not an empty `rows: []` — `refused: true` plus a
`refusal` object with `n`, `threshold`, and `message`, checked before rows in the view so a
client cannot mistake it for "no terms found." A dedicated `role="status"` panel renders it,
styled distinctly from both the error state (red, `role="alert"`) and the empty state (neutral).

### Gates

```
ruff + mypy                                       clean
env -u OPENAI_API_KEY pytest backend/tests -q     263 passed        # was 254
frontend: tsc + vitest + build                    62 passed         # was 59
```

Mutation check on the refusal itself (`if n >= settings.min_n` → `if n >= 0`): 5 of 6 refusal
tests fail, confirming the gate is what they actually test rather than an artifact of the stub.

## #24 — NL to Cube selection, enum-constrained · #25 — filter-value resolution

**#24.** `POST /agent/select` reads Cube's live `/meta`, builds a JSON schema whose measure and
dimension fields are `enum` arrays from that vocabulary, and gets a structured-output selection
back from the model — never a number. The number always comes from `cube_client.query()`
executing the *validated* selection, same as every other endpoint.

```
$ curl -s -X POST localhost:8000/agent/select -d '{"question":"how many matters are there"}'
{"selection": {"measures": ["deal_points.matters_total"], ...},
 "rows": [{"deal_points.matters_total": "152"}]}

$ curl -s -X POST localhost:8000/agent/select -d '{"question":"count of matters by industry"}'
{"selection": {"measures": ["deal_points.count_distinct_matters"],
               "dimensions": ["comparable_deals.label"]},
 "rows": [{"comparable_deals.label": "Health Care Industry",
           "deal_points.count_distinct_matters": "25"}, ...]}
```

25 matches the facet count exactly — same number, same definition, because it's the same query
path. A third live query (filtering `deal_points` by `comparable_deals.label`) hit a real Cube
join-path limit and came back as a 503 with the standard error envelope, not a wrong number or a
500 — the enum guarantees the *names* exist, not that every name pairing is jointly queryable,
and the failure mode for the gap is exactly the one this app uses everywhere else.

Server-side validation is defense in depth: the schema should make an invalid name
undecodable, and a test proves the rejection path never reaches `cube_query()` (monkeypatched
`cube_query` records zero calls on an invalid stubbed selection). "No number from the model" is
its own test: `select_via_llm` is stubbed to return a selection containing no numbers at all,
and `152` is asserted absent from the response's `selection` field — the only place `152` can
come from is the `cube_query` stub.

No key → 503, not a silent skip. 12 tests run keyless (vocabulary parsing, schema shape,
validation, the no-number guarantee); one real call is marked `needs_key` and passed against
live Cube and the actual API key configured in this environment.

**#25.** `resolve_filter_value()` — exact → alias → embedding, first match wins, unresolved
fails loud with candidates. Extended `warm_cache` to embed the corpus's actual industry labels
(14, not the 18k-concept ontology) plus a handful of representative free-text terms, so the
embedding tier runs from the committed cache with no key at test time.

The similarity floor was measured, not guessed, and the first guess (0.35) was wrong:

```
'healthcare'                   -> Health Care Industry            0.602  (real hit)
'not a real industry at all'   -> Real Estate, Rental and Leasing 0.493  (false positive)
'medical devices'/'life sciences'/'pharma' -> 0.35-0.43            (real near-misses)
```

At 0.35, the nonsense phrase resolves to a real industry — a silent wrong answer, the exact
failure this module exists to prevent. Floor set to 0.55: clears every observed real hit,
refuses the false positive and the ambiguous near-misses. Refusing a resolvable value costs a
retry; a false resolution looks like a right answer and is far worse.

```
$ curl -s -X POST localhost:8000/agent/resolve-filter-value -d '{"value":"healthcare"}'
{"raw": "healthcare", "resolved": "Health Care Industry", "method": "embedding",
 "matter_count": 25, "similarity": 0.6025}

$ curl -s -o /dev/null -w '%{http_code}' -X POST .../resolve-filter-value \
    -d '{"value":"not a real industry at all"}'
422
```

### Gates

```
ruff + mypy                                        clean
env -u OPENAI_API_KEY pytest backend/tests -q       281 passed, 1 deselected   # was 270
env pytest backend/tests -q -m needs_key            1 passed
frontend                                            unchanged (backend-only issues)
```

## #26 — ResolvedQuery component · #27 — offline measure-selection eval

**#26.** `ResolvedQuery.tsx` renders every component of a selection in plain language — measure,
dimensions, filters (raw text struck through, resolved value shown after `→`), time range, `n`,
and an `inferred` flag — plus an "edit this query" button. Not wired into a page: the six-tab
set is fixed and load-bearing (`tabs.ts`), and none of the six is an agent surface. Built and
tested as a standalone component per the AC rather than inventing a seventh tab.

**#27.** 25 authored cases (`docs/eval/measure_selection.json`, ≥3 refusals), graded offline
against real recorded `gpt-4o-mini` output (`docs/eval/recorded_outputs.json`) with no network
at grading time — asserted directly by making `socket.socket` raise mid-run.

```
measure_precision 0.800   measure_recall 0.775
dimension_precision 0.692 dimension_recall 0.725
filter_exact_match_rate 0.500
refusal_accuracy 0.200   (1 of 5)
```

The first live recording caught the model selecting `mean_numeric_value_do_not_use_for_market`
for "the average reverse termination fee" — the exact trap that measure's name exists to warn
against, on the first run of the eval built to catch it. Fixed structurally: excluded from the
agent's vocabulary in `fetch_vocabulary()`, not just left as a scary name inside an enum that
still made it selectable. Re-recorded; that case now selects the correct median measure.

Refusal accuracy (0.2) is the real finding, not measure selection: in 4 of 5 cases the model
answered a question it should have declined — filtering `acquirer_name` for "opposing counsel,"
`target_name` for a partner's name — silent reinterpretation rather than declining, which is
exactly what #26's resolved-query line exists to let a human catch downstream. Not fixed here;
noted as the clear next step rather than chased against this specific 25-question set, which
would overfit the eval instead of improving the agent. Full findings, per-case detail, and the
filter-exact-match miss pattern (confusing the boolean `has_industry` with the `label` dimension
— #25's failure mode one level up) are in `docs/results/measure-selection.md`.

### Gates

```
ruff + mypy                                        clean
env -u OPENAI_API_KEY pytest backend/tests -q       289 passed, 1 deselected   # was 281
frontend: tsc + vitest + build                      68 passed
```

## #28 — Calibration: extractor vs held-out MAUD labels

No production extraction pipeline exists in this app (MAUD's labels are loaded, not
re-extracted). This measures a minimal GPT-4o-mini extractor against 20 held-out matters
(`docs/eval/calibration_split.json`, deterministic `sha256(matter_id)` split, committed) across
5 deal points chosen — before any prediction ran — for having a small closed position vocabulary.

```
$ PYTHONPATH=backend python -c "from explorer.evals.calibration import record_predictions; record_predictions()"
$ PYTHONPATH=backend python -m explorer.evals.calibration

Announcement, pendency or consummation of deal (Y/N)   n=20  0.950  CI[0.764, 0.991]  reportable
Acquisition Proposal publicly disclosed (Y/N)           n=20  0.500  CI[0.299, 0.701]  not reportable
"Ability to consummate" subject to MAE carveouts        n=20  0.300  CI[0.145, 0.519]  not reportable
Action prohibited/omission required                     n=20  0.300  CI[0.145, 0.519]  not reportable
Actions taken by Buyer-Answer (Y/N)                     n=20  0.200  CI[0.081, 0.416]  not reportable
```

95% Wilson interval (stable at small n and near 0/1, unlike the normal approximation). 4 of 5
deal points fall below `min_extraction_confidence=0.7`'s lower CI bound and are correctly marked
not reportable — the honest result, published as-is. One deal point (near-universal boilerplate,
well inside the 12k-character context window) generalizes; the other four require reading
covenant language the truncated context often doesn't reach, or a legal distinction (e.g.
Constructive vs. Actual knowledge — the same pair #21's drill-through surfaced as real and
subtle) the minimal extractor wasn't built to make.

Cost: 317,553 total tokens over 100 predictions, measured from `response.usage`. Input/output
split wasn't captured, so cost is a bound rather than a false-precision figure: $0.048–$0.190
at gpt-4o-mini pricing read from developers.openai.com/api/docs/pricing on 2026-07-30
($0.15/$0.60 per 1M input/output tokens), actual likely near the low end given ~3000-token
context per call against a short structured-output completion.

Full analysis, the exact per-case table, and what this accuracy does and does not generalize to
are in `docs/results/calibration.md`.

### Gates

```
ruff + mypy                                        clean
env -u OPENAI_API_KEY pytest backend/tests -q      296 passed, 1 deselected   # was 289
```

### Not done

- 5 of 92 deal points — the easiest by position-vocabulary shape, a real sampling bias toward
  the easy end of the task. Full coverage is materially more cost/time than this issue's scope.
- No attempt to improve the extractor after seeing the numbers — #28 asks for the measurement,
  not a target score, and a worse-than-hoped result is the finding, not something to iterate
  away before publishing (CLAUDE.md).

## #29 — Label review queue · #30 — Admin (ingest, calibration, evals, logs)

**#29.** Queue built from #28's already-committed LLM predictions (no new API call to serve it)
scored against a free keyword-count baseline extractor, ranked by disagreement between the two —
the AC's own point: disagreement needs no calibrated confidence, the cheapest useful signal
before #28 has measured one for a given deal point.

```
$ curl -s localhost:8000/label/queue
queue_size: 100  labelled_count: 0
disagreement items: 15 of 100
```

Accepting an item writes to `labels` (`target_kind='deal_point'`, `field='position'`, prior
prediction recorded), verified with a real row:

```
$ curl -s -X POST localhost:8000/label/decide -d '{...}'
{"ok": true}
$ psql ... select * from labels;
deal_point | contract_10:Acquisition Proposal required to be publicly disclosed... | position | Yes | No | local
```

Keyboard-only (`y`/`n`/`e`/`s`/`?`), no confirmation dialog — every key either posts a decision
or explicitly skips and advances, which is what "under 5 seconds per item" actually requires.

**#30.** Composition, not new computation — every number here is read from an artefact another
issue already produces (`ingest_runs`, `docs/results/*.md`), so there's exactly one place any of
them can drift from what actually ran.

```
$ curl -s localhost:8000/admin/ingest-status | # per-source latest run
cuad: 13823 rows, 755ms, sha f8161d18...
```

Log viewer measured against the real file this session accumulated — **15,784 lines**, not a
synthetic fixture — paginated query returned in **87ms**. Redaction verified with an actual
`sk-proj-` shaped fake key: the viewer re-redacts defensively on top of the write-time structlog
processor (D5), since it must not trust that every line on disk went through that pipeline.

**A Dockerfile gap found and fixed**, same class as #20's `source_file` path bug: neither
`admin.py` nor `label.py` could read anything, because the `api` image never `COPY`'d `docs/` —
both 404'd until the Dockerfile was corrected.

`git_sha` reports `"unknown"` inside the container (no `.git` in the image) and the real short
SHA locally — a stated, not hidden, limitation of the containerized deployment.

### Gates

```
ruff + mypy                                        clean
env -u OPENAI_API_KEY pytest backend/tests -q      313 passed, 1 deselected   # was 296
frontend: tsc + vitest + build                     81 passed                 # was 68
```

## #31 — Tables: browsable raw data so nobody opens psql

Generic `GET /tables/{table}/{schema,rows,rows/{id},export.csv}` over a whitelist of six tables.
Every identifier (table name, sort column, filter column) is checked against
`information_schema` before it can reach a query string; every value is a bound parameter.

```
$ curl -s "localhost:8000/tables/matters%3B%20DROP%20TABLE%20matters/rows" -> 404
$ curl -s "localhost:8000/tables/matters/rows?sort=id%3B%20DROP%20TABLE%20matters" -> 422
$ psql ... select count(*) from matters;  -> 152   # unaffected
```

Real row counts, measured against the running stack:

```
matters 152 · deal_points 12937 · clauses 13823 · folio_concepts 18259 · labels 1 · ingest_runs 462
```

`limit` is capped server-side at 500 and **rejected, not silently clamped**, above that — the AC
is "the frontend never loads a whole table," and a silent cap would let a caller believe it
received everything when it did not. CSV export bypasses the pagination ceiling deliberately
(it exists to download the current filtered view) but is capped at 50,000 rows as a safety valve,
verified with a real multi-column export against `matters`.

Column headers show live type + null count from `information_schema`, not asserted — e.g.
`deal_value_usd: numeric · null=152`, the #9 gap made visible generically rather than special-
cased. `is_inferred_*` columns are flagged the same way the matter card (#20) flags them, read
by naming convention rather than hardcoded per table, so a new inferred column is flagged
automatically. Sort/filter/page state mirrors into the URL query string via
`history.replaceState` — no router needed for a single-page shell.

### Gates

```
ruff + mypy                                        clean
env -u OPENAI_API_KEY pytest backend/tests -q      326 passed, 1 deselected   # was 313
frontend: tsc + vitest + build                     86 passed                 # was 81
```

## #32 — Walkthrough: three worked examples, real observed output

`docs/walkthrough.md`, run against the live stack this session — not a script written first and
back-filled. Terminal transcripts committed under `docs/results/walkthrough-script{1,2,3}.txt`.

Script 1 (Explore): landing counts (152/12,937/14) → Health Care facet (n=25, self-filtering
verified) → 8 ranked comparables, `candidate_count=25` matching the facet count exactly.

Script 2 (Deal Terms): the same 8 matters rolled up (`answered=90`, zero rows render as a
percentage at n=8) → `Knowledge Definition-Answer` splits 5 Constructive / 3 Actual across the
8 → drill-through to the actual clause language, byte-verified against the downloaded contract,
showing *why* the two contracts read differently ("reasonable inquiry" is the distinguishing
phrase).

Script 3 (refusal): Coverage's real thin-cell count (33 of 45) → a 3-matter Deal Terms request
refused (`n=3 < min_n=5`, distinct response shape) → the gate proven server-side with two direct
curl attempts (empty selection → 422; extra `admin`/`bypass_min_n` fields → still refused,
because nothing reads them) → the three-jobs-at-once rationale (statistical honesty, extraction
confidence, k-anonymity) stated alongside the numbers, not left implicit.

Linked from the README under a new "Walkthrough" section.

### Gates

No code changed — documentation only, verified against the already-green stack.
| D46 | The Semantic Layer tab reads Cube's `/meta` **live**; the freeform text-to-SQL arm is generated but **never executed** | A checked-in catalog can drift from `cube/model/*.yml`, and then a selection failure becomes an unfalsifiable argument about which list was authoritative. The freeform arm is not executed because the honest claim is not "its SQL is wrong" — it is often right — but that two freeform queries can only be diffed, never scored | The tab hard-depends on Cube being up and cannot degrade to a cached vocabulary; and the comparison is rhetorical rather than empirical, which a sceptical reviewer may fairly push on |

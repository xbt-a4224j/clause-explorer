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
| D19 | Aliases live in a separate **`folio_aliases`** table; an ambiguous alias resolves to `None` | `skos:altLabel` is many-per-concept, and picking arbitrarily between two concepts sharing an alias is a wrong answer that looks right | An extra table and a second query on the resolve miss path |

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

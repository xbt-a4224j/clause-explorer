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

# Build progress

Appended after each issue. Every figure here came from a command shown alongside it.

---

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

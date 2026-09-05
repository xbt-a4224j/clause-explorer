.PHONY: up down test check eval ingest logs fmt

up:            ## boot the whole stack
	docker compose up --build

down:
	docker compose down

ingest:        ## idempotent load: FOLIO -> MAUD -> EDGAR enrich
	PYTHONPATH=backend python -m explorer.ingest --source $(or $(SOURCE),all)

test:          ## everything that runs with no API key
	pytest backend/tests -q -m "not needs_key"
	cd frontend && npm test -- --run

check:         ## what CI enforces
	ruff format --check .
	ruff check .
	mypy backend/explorer --ignore-missing-imports
	cd frontend && npx tsc --noEmit
	$(MAKE) test

eval:          ## calibration + measure-selection harnesses; writes docs/results/
	PYTHONPATH=backend python -m explorer.evals --all --out docs/results

logs:
	tail -f logs/explorer.jsonl

fmt:
	ruff format .
	cd frontend && npx prettier --write src

migrate:       ## apply schema (up|down|reset via ARG=)
	PYTHONPATH=backend python -m explorer.db.migrate $(or $(ARG),up)

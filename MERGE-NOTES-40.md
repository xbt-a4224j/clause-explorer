# Merge notes — #40 (drop CUAD)

I did not edit `README.md`; another process owns it. This lists exactly which README passages
my change makes wrong, and what they should say. Line numbers are against `README.md` at
`9c83106`.

## 1. Data table — the CUAD row comes out (line 129)

Currently:

```
| [CUAD](https://www.atticusprojectai.org/cuad) | commercial contracts, 41 expert-annotated clause types | CC BY 4.0 |
```

**Delete the row.** The table then lists three sources: MAUD, FOLIO, SEC EDGAR. Nothing else in
that table changes — no MAUD, FOLIO or EDGAR figure moved.

## 2. Limitations — the CUAD entry comes out (lines 158–160)

Currently:

```
- **CUAD is loaded and unused.** 13,823 clauses with provenance, attached to no matter, visible
  only in Tables. Mixing 510 commercial contracts into "comparable deals" would inflate every
  facet count. No CUAD row has an industry.
```

**Delete the whole bullet.** It is no longer a limitation because the thing it describes no
longer exists. Do not replace it with a "CUAD was removed" bullet — the Limitations list is for
things that are true of the shipped system. The removal note lives in `docs/provenance.md`
(under `## CUAD — removed`) and in a comment at the top of `backend/explorer/db/schema.sql`.

## 3. Quickstart — the ingest comment (line 188)

Currently:

```
make ingest               # FOLIO -> MAUD -> EDGAR enrich -> CUAD, idempotent
```

Should read:

```
make ingest               # FOLIO -> MAUD -> EDGAR enrich, idempotent
```

Verified: `python -m explorer.ingest` with the default `all` now runs exactly
`["folio", "maud", "edgar"]`, and `--source cuad` is rejected by argparse.

## 4. License — the attribution list (line 206)

Currently:

```
Code MIT. Corpora are CC BY (MAUD, CUAD, FOLIO) — attribution and provenance, including download
commands and checksums, in `docs/provenance.md`.
```

Should read `(MAUD, FOLIO)`. CUAD is no longer redistributed, ingested or downloaded by anything
in the repo, so the attribution obligation no longer attaches. `scripts/download_cuad.sh` is
deleted.

## 5. Clause counts — what changed and what did NOT

- **The only count that changes is the clause count: 13,823 → the table is gone.** There is no
  replacement number. Any "13,823" in README text should be deleted, not adjusted.
- **A "six tables" claim becomes five.** I did not find one in README.md, but I did fix three
  elsewhere (`explainers.tsx`, `diagrams.tsx`, the architecture `<desc>`). Grep the README for
  "six" before merging.
- **Nothing else moved.** 152 matters, 12,937 deal points, 92 deal point names, 18,259 FOLIO
  concepts, 134 of 152 with an industry, 12,442 located spans, 495 (3.8%) NULL spans — all
  unchanged, re-verified by a full ingest into an isolated database (see below).
- Line 151's "Most recorded spans are not clauses" bullet is about **deal-point** spans, not the
  `clauses` table. It stays exactly as written.

## Not mine to fix: one CUAD mention left in `docs/results/calibration.md`

Line 97 reads:

```
- non-merger commercial contracts (CUAD's domain), a different document type entirely
```

That file belongs to the Label-loop ticket (#41), so I backed my edit out rather than create a
conflict over a parenthetical. The parenthetical should become nothing — the sentence reads
correctly as `- non-merger commercial contracts, a different document type entirely` — but it is
#41's line to change. It is the only CUAD reference left in the repo outside the deliberate
removal notes and `docs/ownership-tasks.html` (see below).

## Also left alone: `docs/ownership-tasks.html`

That file records a past hands-on investigation with its real `psql` output, including the rows
that prove `clauses` was 100% CUAD with a NULL `matter_id`. It is a dated record of what was
observed, not documentation of the current system. Editing it would falsify the record, so I
left it. It is the evidence for this ticket's central decision.

## Verification behind these notes

Isolated database `explorer_40`, never `explorer`:

```
$ python -m explorer.ingest --source cuad          # before the change
{"source": "cuad", "contracts": 510, "clauses": 13823, "clause_types": 41, "with_industry": 0}

$ psql -d explorer_40 -Atc "SELECT corpus, count(*) FROM clauses GROUP BY 1;"
cuad|13823

$ python -m explorer.db.migrate up                 # after the change
{"tables": 6, "event": "migrate_up"}
$ psql -d explorer_40 -Atc "SELECT count(*) FROM clauses;"
ERROR:  relation "clauses" does not exist

$ python -m explorer.ingest                        # default 'all', after the change
{"sources": ["folio", "maud", "edgar"], "event": "ingest_complete"}
```

The same read-only query against the shared `explorer` database returned `cuad|13823` and
`0` rows with a non-NULL `matter_id`, which is the evidence for dropping the table rather than
keeping it — see the decision note below.

## Decision: the table went, it was not just emptied

`clauses` held 13,823 rows, **every one `corpus='cuad'`**, every one with `matter_id` NULL. No
MAUD rows were ever written to it: `maud.py` writes only `matters` and `deal_points`, and
`cuad.py` was the sole `INSERT INTO clauses` in the codebase. So the ticket's conditional
resolved to "else it goes too", and the table is dropped by
`DROP TABLE IF EXISTS clauses CASCADE` at the top of `schema.sql`.

**Cost accepted.** `schema.sql` is applied idempotently rather than as a revision chain, so the
drop has to live in the schema file itself and runs on every `migrate up` forever. That is a
destructive statement in a file people re-run casually. It is also the only way an already
migrated database actually loses the table. If clause-level storage returns, it must come back
as a new table definition placed *below* that line, and whoever does it has to notice the drop
first. A dated migrations directory would be the better home for this; introducing one for a
single statement was more machinery than the change justifies.

**Second cost.** `data/embeddings/vectors.npz` is committed and still contains `clause:*`
vectors that nothing will ever look up now. Regenerating it needs `OPENAI_API_KEY` and would
rewrite a version-controlled artifact, which `warm_cache.py` documents as a deliberate-only
action. I left the file untouched: the stale entries are unreachable dead weight, not a
correctness problem. Whoever next runs `warm_cache` with a key will drop them for free.

# Merge notes — #49, drop the FOLIO ontology

Written because this branch was not permitted to edit `README.md` or six frontend files that
other agents own this round. Everything below is work #49 made necessary and did **not** do.
Delete this file once the list is cleared.

## README.md — five passages this change makes wrong

`README.md` was not touched. These are the exact edits it needs.

1. **Line 131, the Data table.** The row

   ```
   | [FOLIO](https://github.com/alea-institute/FOLIO) | 18,000+ legal concepts in OWL — the dimension vocabulary | CC BY |
   ```

   should be **deleted**, not reworded. FOLIO is no longer a data source: nothing downloads it,
   nothing parses it, and no table holds it. The industry vocabulary now comes from
   `data/mappings/sic_to_folio.csv`, which is a checked-in derived file already described in the
   EDGAR section of `docs/provenance.md` rather than a third-party corpus with its own licence
   row. If a row is wanted in its place, it belongs under SEC EDGAR, not beside MAUD.

2. **Line 144, Limitations — "Industry is inferred, on every matter."** Reads "A checked-in SIC
   to FOLIO crosswalk over the SEC's self-assigned code resolves 139 of 152." Should read "A
   checked-in SIC industry crosswalk over the SEC's self-assigned code resolves 139 of 152."
   The 139-of-152 figure is **unchanged** and re-measured today — see below. So is the "26
   matters" Health Care figure in the same bullet.

3. **Line 179, Stack.** Drop `rdflib` from the list. It was there for the OWL parse and is
   removed from `requirements.txt` in this change.

4. **Line 198, Quickstart.** `make ingest  # FOLIO -> MAUD -> EDGAR enrich, idempotent` should
   read `make ingest  # MAUD -> EDGAR enrich, idempotent`. `--source folio` no longer exists;
   the CLI's sources are `maud`, `edgar`, `all`.

5. **Line 216, License.** "Corpora are CC BY (MAUD, FOLIO)" should read "Corpora are CC BY
   (MAUD)". The FOLIO attribution has not been dropped — it moved to the single provenance
   paragraph recording that the ontology was evaluated and removed, because the industry codes
   in the crosswalk are still FOLIO IRI suffixes.

**The Limitations inert-hierarchy bullet is already gone.** The brief said Limitations carries a
bullet explaining that the hierarchy does nothing, to be deleted rather than reworded. Grepping
`README.md` for `hierarch`, `roll-up`, `rolls up` and `inert` returns nothing, so a previous
round removed it. Nothing to do; noted so the absence is not read as an oversight.

**No caption names FOLIO.** The seven image captions were checked individually; the only
industry claims they make ("139 filterable", "Thirteen matters have no industry", "INFERRED")
are all still true after the re-ingest.

## Frontend files this branch was told not to touch

### `frontend/src/views/Tables.tsx` — a real bug if this file survives merge

Line 8:

```ts
const TABLE_NAMES = ['matters', 'deal_points', 'folio_concepts', 'labels', 'ingest_runs']
```

`folio_concepts` no longer exists and is no longer in `api/tables.py`'s `ALLOWED_TABLES`, so
selecting it in the Tables view now gets a 404. It must become `'industries'`. Its test
(`Tables.test.tsx`) *was* updated here, because it asserted the explainer prose names a table
that no longer exists and would otherwise have failed the gate.

If `Tables.tsx` is being deleted this round, nothing to do.

### `frontend/src/views/Coverage.tsx`, `journeys.ts` — wire field names

The API still sends `folio_industry_code` / `folio_industry_label` on `/comparables`,
`/facets` and `/coverage`. The database column is `industry_code` and the Cube dimension is
`industry_code`; only the JSON field names still say `folio_`. That was deliberate: renaming
them is a change to `Coverage.tsx`, `journeys.ts` and `Explore.tsx`, and two of those were off
limits. Shipping a rename that breaks a view is worse than shipping a field name that reads
oddly.

**The follow-up:** rename the wire fields to `industry_code` / `industry_label` in one commit
touching `api/comparables.py`, `api/facets.py`, `api/coverage.py`, `types.ts`, `journeys.ts`,
`Explore.tsx` and `Coverage.tsx` together. `api/comparables.py` and `api/facets.py` carry a
comment at the field pointing here.

### Comments that still say FOLIO in off-limits files

Cosmetic, no behaviour attached, left alone because these files may not survive the round:

- `Coverage.tsx` line 9: `Coverage — FOLIO industry × period, for KM triage (#22).`
- `Coverage.test.tsx` lines 11 and 125: "a click carries a FOLIO code".
- `journeys.ts` line 45: `/** FOLIO code for Health Care Industry, joined on rather than matched
  by label (#18). */` — the sentence after the comma is the property #49 kept and is still
  correct; only the word FOLIO is stale.

## Stale numbers found but not corrected (out of scope, no FOLIO in them)

Both are in files this branch edited, in paragraphs that did **not** name FOLIO, so they were
left rather than widened into someone else's diff:

- `frontend/src/components/Term.tsx`, the **EDGAR** glossary entry: "134 of 152 resolved to an
  industry". Measured today: **139 of 152**.
- `frontend/src/components/explainers.tsx`, `ExploreExplainer` limits paragraph: "134 of
  152 resolved". Same correction.

The two that *were* in FOLIO copy were corrected: the facet-rail note in `QueryBuilder.tsx`
said "18 of 152 agreements could not be resolved" and now says 13, and the Tables explainer
said `folio_concepts` (18,259) and now says `industries` (20).

## `docs/results/walkthrough-script1.txt` — needs re-recording, not editing

Line 22 of the recorded transcript contains

```
applied: {..., "rolled_up_to_descendants": 91, ...}
```

`/comparables` no longer emits that field. This file is **recorded output from a live stack**,
so hand-editing it would fabricate a command result, which CLAUDE.md forbids outright. It has
to be re-recorded by re-running `docs/walkthrough.md`'s script 1 against the stack once Cube
and the `explorer` database have picked up the #49 model. This branch could not do that: it was
required to leave the `explorer` database and the Cube container on :4000 alone.

## Decisions, with the cost accepted

| # | Decision | Why | Cost accepted |
|---|---|---|---|
| 1 | `data/mappings/sic_to_folio.csv` left byte-identical — filename, `folio_code`/`folio_label` headers and curation comments | #49 names that exact path as the thing that survives, and the codes in it *are* FOLIO IRI suffixes: the header block is the audit trail a reviewer uses to check a single row | "FOLIO" survives in one data file's name and comments. A reader greping for FOLIO finds it and has to read the provenance paragraph to learn why |
| 2 | Wire field names stay `folio_industry_code` / `folio_industry_label` | Renaming them requires editing `Coverage.tsx` and `journeys.ts`, which this branch was told not to touch. Shipping a rename that 404s a view is worse than an odd field name | The API surface still says FOLIO after the ontology is gone. Two comments point at this file; the follow-up is scoped above |
| 3 | `matters.folio_service_code` and `is_inferred_service` dropped, not kept as plain TEXT | Both existed only for a second FOLIO branch that was never loaded, never written and never read; the column's foreign key pointed at a table that no longer exists | If a service-code dimension is ever wanted it is a new migration rather than a column already in place. Given nothing ever wrote it, that is the honest starting point anyway |
| 4 | The `industries` foreign key on an already-migrated database is added `NOT VALID` | The seed runs at ingest and the migration runs before it, so validating at migrate time fails on ordering, not on data. Same pattern the file already uses for `deal_points_span_kind_ck` | Rows written before #49 are not checked against the constraint. Every write from here on is. A full re-ingest was run and every one of the 139 codes resolves, so the unchecked set is known-good rather than assumed-good |
| 5 | `industries` is seeded by the EDGAR step, not by a new `--source industries` | EDGAR already reads the crosswalk and already writes the codes, so the vocabulary and the rows that reference it are written in one step and the foreign key can never be unsatisfiable | The ingest CLI no longer has a step whose only job is the vocabulary, so `ingest_runs` shows the seed as part of the `edgar` row (`detail` names the count) rather than as its own row |
| 6 | `docs/results/walkthrough-script1.txt` left stale rather than edited | It is recorded output from a live stack; hand-editing it fabricates a command result | The committed transcript shows a `rolled_up_to_descendants` field the API no longer emits until someone re-records it |

## One test skips until Cube reloads

`backend/tests/test_cube_model.py::TestAgainstLiveCube::test_a_matter_filter_constrains_a_deal_point_rollup`
filters on `industries.label`, which the container serving the pre-#49 model does not expose. A
`_cube_serves("industries")` guard skips it in that state, in the same style as the existing
`_cube_up()` guard. Nothing about what the test asserts was relaxed. After Cube reloads the
model the guard passes and the test runs; if it is still skipping a week from now, that is a
signal the container never picked the model up.

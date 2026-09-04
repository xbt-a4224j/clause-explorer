# Merge notes — #44 onto integration, and the two stale artifacts it exposed

Written because this merge must not touch `README.md`. Everything below is either a request to
the README's owner or a record of what was measured, with the command that produced it.

This is the seventh branch onto `integration`: `worktree-agent-a7c235b32dff33012` (#44,
"calibrate all 92 deal points") merged onto a base that already carried #41 ("close the Label
loop"). It conflicted in five files. It also forced the two items `MERGE-NOTES-42.md` left open,
because they could not be closed from #42's own branch.

## 1. The label loop's numbers, regenerated

`docs/results/calibration-labels.json` was committed by #41 against #28's **100** predictions.
#44 replaced `docs/eval/calibration_predictions.json` with **1,701** predictions from a changed
answer channel (the enum now carries short option ids, not the position prose), so #41's figures
described nothing on disk. #41's own tests for `score()` are fixture-based and stayed green
throughout — nothing failed to warn anyone, which is why this had to be done by hand.

```
$ PYTHONPATH=backend python -m explorer.evals.calibration
correct 569 of 1701 before, 565 of 1701 after; 6 labels applied, 5 differing
```

| | #41 as committed | regenerated on the merged code |
|---|---|---|
| predictions | 100 | **1,701** |
| correct before labels | 45 | **569** |
| correct after labels | 44 | **565** |
| accuracy before / after | 0.450 / 0.440 | **0.335 / 0.332** |
| labels applied | 6 | 6 (unchanged rows in `labels`) |
| labels differing from the model | 2 | **5** |

**The delta is negative and it is bigger than #41's, on a denominator seventeen times larger:
−4 correct answers, not −1.** No tuning was applied and nothing was seeded. On the wider run the
extractor is *right* on four of the six pairs a reviewer touched, and all four of those labels
are wrong against MAUD — three literal `No`s and one half-typed `N` where gold is `Yes`. The
fifth differing label is `s`, a stray keystroke. The per-pair table is in
`docs/results/calibration.md`.

That is the substitution rule behaving as #41 specified: a label *replaces* the prediction and is
graded like any other answer. A loop that could only report improvement would be a loop worth
distrusting. It is not evidence that human review helps — these six decisions were made to prove
the Label tab wrote rows, and the grader is not permitted to know that.

`docs/results/calibration.md`'s main results table is now the **graded** number, so it includes
those labels. Two rows moved relative to #44's committed table: `Acquisition Proposal required to
be publicly disclosed-Answer (Y/N)` 13 → 10 correct, and `Action prohibited/omission required by
the agreement-Answer` 6 → 5. Every headline in the "finding" section survived unchanged: 5 of 90
clear the 0.70 lower-bound gate, 13 clear it on the point estimate, median accuracy 0.25, 6 deal
points at 0.000, 77 of 90 below 0.70.

## 2. The #42 leftovers, both closed

`MERGE-NOTES-42.md`'s BLOCKER section listed two things #42 could not do from its own branch.
Both are done. The shared `explorer` database had never been re-ingested with #42's EDGAR rule —
it still carried the pre-#42 distribution — so the first step was `python -m explorer.ingest
--source all` against it, which reported `with_folio_industry: 139` and `network_requests: 0`.

### Embedding cache re-warmed

```
$ PYTHONPATH=backend python -m explorer.retrieval.warm_cache
{"texts": 265, "already_cached": 176, "event": "warm_cache_start"}
{"model": "text-embedding-3-small", "dimensions": 256, "texts": 89, "tokens": 3985,
 "event": "embeddings_created"}
{"texts_seen": 265, "embedded_now": 89, "entries_before": 11894, "entries_after": 11980,
 "api_calls": 1, "file_bytes": 10163832}
```

**89 texts, 3,985 tokens, 1 API call.** At text-embedding-3-small's $0.02 / 1M tokens that is
**$0.00008**. The missing count was measured offline first, against the committed `vectors.npz`,
before anything was spent; an upper bound of $0.0001 authorised the run. `data/embeddings/vectors.npz`
is committed in this merge, 11,894 → 11,980 entries.

### The stale assertions

`MERGE-NOTES-42.md` predicted five sites. Nine assert lines across seven tests actually failed,
each updated to the number watched go green against the re-ingested database:

| file:line | assertion | old | new |
|---|---|---|---|
| `test_comparables.py:57` | Health Care `candidate_count` | 25 | **26** |
| `test_comparables.py:79` | every classified matter, `candidate_count` | 134 | **139** |
| `test_cube_model.py:239` | `counts["Health Care Industry"]` | 25 | **26** |
| `test_cube_model.py:240` | `counts["Finance and Insurance Services Industry"]` | 25 | **24** |
| `test_cube_model.py:262` | `by_flag["false"]` (no industry) | 18 | **13** |
| `test_cube_model.py:263` | `by_flag["true"]` (classified) | 134 | **139** |
| `test_cube_model.py:293` | health-care deal-point rollup total | 25 | **26** |
| `test_filter_resolution.py:53` | exact-tier `matter_count` | 25 | **26** |
| `test_filter_resolution.py:119` | embedding-tier `matter_count` | 25 | **26** |

`test_facets.py:195`, `test_facets.py:207` and `test_coverage.py:103` were on #42's list but were
left alone: they run against `StubCube`, so their numbers describe the fixture and not the
corpus. They passed throughout.

Stale prose corrected alongside them, all of it naming 134: `backend/explorer/api/facets.py:117`
(a message a user can see), `cube/model/matters.yml` twice, and two test docstrings.

**One correction to `MERGE-NOTES-42.md`.** Its distribution table says "every other industry is
unchanged". Business and Administrative Services Industry went **7 → 6**. Measured after ingest:

| industry | before | after |
|---|---|---|
| Health Care | 25 | 26 |
| Information | 18 | 25 |
| Finance and Insurance Services | 25 | 24 |
| Manufacturing | 22 | 22 |
| (unclassified) | 18 | **13** |
| Mining and Natural Resources Extraction | 11 | 11 |
| Real Estate, Rental and Leasing | 12 | 9 |
| Business and Administrative Services | 7 | **6** |
| Retail Trade | 3 | 4 |
| Transportation and Logistics | 1 | 2 |

Everything else is unchanged. Both columns sum to 152.

`test_cube_model.py::TestNewRowsAppearWithoutARestart` passes. #42 was right that it fails only
under two-database isolation; with Cube and the API on one database it is green.

## 3. What the README must say

The README is stale in ways this merge makes concrete. Each item below has a command behind it.

### `## Limitations` — replace three bullets

Current:

> - **Industry is inferred, on every matter.** A checked-in SIC to FOLIO crosswalk over the SEC's
>   self-assigned code resolves 134 of 152. A 20-matter hand check found the registrant was the
>   target in 17 and the acquirer in 3. The grouping is ours: it puts pharma, biotech, devices and
>   CROs under Health Care (25 matters); straight NAICS would leave Health Care at 3.

Suggested (the 19/1/0 hand check is #42's, not re-run here; the counts are mine):

> - **Industry is inferred, on every matter.** A checked-in SIC to FOLIO crosswalk over the SEC's
>   self-assigned code resolves 139 of 152. The registrant is constrained to the deal's *target*
>   using MAUD's own `<Target>_<Acquirer>` deal name, so the buyer's industry cannot land on the
>   seller's deal; a matter whose target does not resolve keeps NULL. A 20-matter hand check found
>   the registrant was the target in 19 and NULL in 1, with 0 acquirers. The grouping is ours: it
>   puts pharma, biotech, devices and CROs under Health Care (26 matters).

Current:

> - **CUAD is loaded and unused.** 13,823 clauses with provenance, attached to no matter, visible
>   only in Tables. Mixing 510 commercial contracts into "comparable deals" would inflate every
>   facet count. No CUAD row has an industry.

**Delete it.** #40 dropped CUAD from ingest, the schema and the UI, and dropped the `clauses`
table with it. Five browsable tables remain: `matters`, `deal_points`, `folio_concepts`,
`labels`, `ingest_runs`. The CUAD row in the Data table and the CUAD attribution in the licence
line should go the same way.

Current:

> - **The Label loop does not close.** Decisions write to `labels`; calibration does not read them.
>   On this corpus it could not usefully: every queued item already has a lawyer's answer.

Suggested:

> - **The Label loop closes, and this corpus cannot benefit from it.** Calibration prefers a
>   Label-tab decision over the model's answer and grades it against MAUD like any other answer —
>   a substitution, not a correction. On the 1,701-prediction run the 6 recorded decisions move
>   the score from 569 correct to 565: five of them differ from the model and four turn a right
>   answer wrong. Every queued item is a held-out matter that already has a lawyer's answer, so a
>   reviewer here can at best reproduce gold. The mechanism is for documents nobody annotated.

Current:

> - **The extractor is mostly below its own gate.** Of 5 calibrated deal points, 4 are under 0.7
>   accuracy (0.50, 0.30, 0.30, 0.20; one at 0.95).

Suggested:

> - **The extractor is mostly below its own gate.** All 92 deal points are now calibrated, not 5.
>   90 are measurable on the committed holdout; **5 of those 90 clear 0.70** on the lower bound of
>   the 95% Wilson interval, 13 clear it on the point estimate, and the median accuracy is 0.25 —
>   6 deal points score 0.000. Measured at $0.854442 over 1,701 calls on `gpt-4o-mini`. The gate
>   does not fire on anything the product serves: every `deal_points` row is a MAUD lawyer
>   annotation, and gating gold data on an extractor's accuracy would suppress the product's own
>   data.

### The Explore screenshot caption, ~line 21

**134 filterable** becomes **139**, and *eighteen* matters with no industry becomes *thirteen*.
`docs/img/explore.png` still shows the old header, so caption and picture disagree until it is
retaken. Not retaken here.

### The Label screenshot caption, ~line 65

"Decisions are recorded; calibration does not read them back yet" is no longer true. Calibration
reads them back; see the bullet above.

### `make ingest` and the Data table

Line 188 still says `FOLIO -> MAUD -> EDGAR enrich -> CUAD`. CUAD is gone from that chain.

## 4. How the five conflicts were resolved

- **`backend/explorer/evals/calibration.py`.** `score()` is now the single pure grader and takes
  both sides' semantics: #41's label substitution and #44's `vocabulary` widening. A deal point
  with no prediction is one row with `measured=False` and `accuracy=None`; `accuracy_before`
  became `float | None` for the same reason `accuracy` did. `grade()` keeps both `use_labels` and
  `vocabulary`. `write_report()` gained an optional `summary` argument so the CLI grades once and
  writes both artefacts from the same numbers — two `grade()` calls could straddle a reviewer's
  keystroke and write two files that disagree. `write_report()` lists measured rows only: an
  unmeasured deal point has no before and no after, and printing zeros there would read as "the
  reviewers changed nothing on it", a different claim from "nobody measured it".
- **`backend/tests/test_calibration.py`, `backend/explorer/api/admin.py`.** Both sides kept whole;
  the conflicts were adjacent additions, not disagreements.
- **`frontend/src/views/Admin.tsx`.** #44's rich `CalibrationReport` replaces the generic
  `ReportSection` (which had no other caller and is deleted); #41's `LabelLoopCalibration` is
  kept beside it. Both were converted to the `AbortController` teardown #38 established for this
  file — #41's arrived on a branch that predated it and used the older `cancelled` boolean.
- **`docs/results/calibration.md`.** #44's structure, #41's before/after section folded in with
  regenerated figures, and the results table regenerated from
  `docs/eval/calibration_accuracy.json`.

## 5. Also fixed, and why it was not optional

`Tables.test.tsx` and `explainers.tsx` were red on `integration` before this merge, from a #40 ×
#45 collision unrelated to #44: the Tables explainer still announced "Six tables — … `clauses`
(13,823, from CUAD) …" after #40 dropped that table, and then contradicted itself two paragraphs
later with "What the five tables are". The test asserted the prose says "CUAD is loaded and no
other tab queries it", which the prose no longer said.

The prose now names the five tables `backend/explorer/api/tables.py` will actually serve. The
test was re-pointed rather than removed: its subject was "do not overstate a loaded-but-unqueried
corpus", and the post-#40 version of that guard is that the corpus must not be named at all. It
now asserts the explainer mentions neither CUAD nor `clauses`, and names all five real tables.

`Admin.test.tsx`'s "keeps its four sections" matched `/calibration/i`, which #41's second
calibration heading makes ambiguous — `findByRole` throws on the ambiguity, not on a missing
section. The matchers are anchored and the labels section added.

## 6. Not done

- **No paid calibration re-run.** The 1,701 predictions are committed and re-grading them is
  free. Nothing in this merge required new predictions.
- **`docs/img/explore.png` not retaken.** It shows the pre-#42 header.
- **The two unmeasured deal points stay unmeasured.** MAUD answers them on no holdout matter.
  Measuring them needs a different split, which would break the committed one's held-out property.
- **`docs/worklog.md` not updated.** Gitignored and shared with the main checkout.
- **Nothing pushed.**
- **An environment trap worth a ticket, not a repo change.** Running the suite ~20 seconds after
  `docker compose restart cube` produced 14 failures spread across `test_comparables`,
  `test_hybrid_retrieval`, `test_cube_model` and `test_filter_resolution` — including
  `TestUncachedQueryWithoutAKey`, which looks like a key-detection bug and is not one. Cube was
  still coming up, and `/comparables` reads candidate counts through it, so a not-yet-ready Cube
  surfaces as retrieval and no-key failures rather than as a Cube error. The same suite on the
  same tree is green once Cube has settled; the first suspect (a `.env` in the worktree) was
  tested directly and ruled out — 410 pass with the file present and with it absent. If the
  suite goes red right after a Cube restart, wait, do not diagnose.

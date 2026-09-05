# Merge notes — wave two (#47, #50, #51, #54)

Written because this round is under instruction **not to touch `README.md`**. Everything below
is a passage the four commits made wrong, or a decision a reviewer would reasonably question.
Nothing here has been applied to the README; it is all yours to reconcile.

---

## 1 · README passages these commits make wrong

### 1a · Keyless operation, advertised as a virtue

`7bc47ee` removed the keyless-boot constraint from `CLAUDE.md`, and #47 put the model on a
user's path, so every claim of the following shape is now either false or beside the point.
Grep for `no API key`, `keyless`, `without a key`, `OPENAI_API_KEY` in `README.md`.

| Passage, in substance | Why it is now wrong | What it should say |
|---|---|---|
| "the app boots and serves everything with no API key" | Ask's question box is the headline feature and it calls a model | An API key is required to run the product. Retrieval, facets, the rollup, the builder and the offline grades still work without one; **asking a question does not**. |
| "retrieval runs with no key because the embedding cache is committed" | Still true, and still worth saying | Keep — but frame it as *reproducibility* (a clone gets identical vectors) rather than as *keyless operation*. |
| "tests run with no key" | True and unchanged | Keep. It is a property of the test suite, not a promise about the product. |

Two in-repo copies of the same claim were **edited rather than left**, because these four
commits are what made them wrong and leaving them would have shipped a false statement on a
tab I was changing:

- `frontend/src/views/Ask.tsx`, the `keyless-note` span. Was "No API key is needed for any of
  that." Now scopes the claim to the catalog, builder and grade, and says the question box
  needs one.
- The `Ask` component docstring, which described the tab as "keyless by design".

`backend/explorer/api/settings.py` still carries this on `openai_api_key`, and I left it —
it is a docstring you may want to reconcile in the same pass as the README:

> Present only so generation and fresh embeddings can work. The app must boot and
> serve retrieval, facets, the rollup and every table view without it.

`backend/explorer/retrieval/embeddings.py`'s module docstring opens with "the reason retrieval
works with no API key" and cites CLAUDE.md for a constraint that no longer exists. The
*mechanism* it describes is unchanged and correct; only the justification is stale.

### 1b · The tab table

`README.md` and `CLAUDE.md` both carry a six-row tab table listing **Admin**. #54 removed
Admin from the bar. The replacement row:

| Tab | For | What |
|---|---|---|
| **Trust** | KM | where the model is trusted and where it is not — calibration, the label loop, selection quality; ingest status and the log viewer collapsed at the bottom |

`CLAUDE.md`'s table also still lists **Coverage** and **Tables**, which #48 removed. Not caused
by this wave, but it is wrong in the same table.

### 1c · "Nothing in the app calls a model"

Any README sentence describing the agent as reachable only from the eval harness is now wrong.
`POST /agent/ask` has a caller and a confirmation step.

### 1d · Layout section

`CLAUDE.md`'s `frontend/src/views/` line reads
`Explore · DealTerms · Coverage · Tables · Admin · Label`. Current:
`Overview · Ask · Explore · DealTerms · Trust · Label`.

### 1e · Figures worth quoting that did not exist before

- measure-selection now has a committed machine-readable summary:
  `docs/results/measure-selection.json`.
- Cost per Ask question, measured: **$0.000125–$0.000147** across the development calls
  (717–726 prompt tokens, 29–64 completion, 1.0–2.7s).

---

## 2 · Things the issues asked for that the data contradicts

**Trust the file, and say so** — as instructed. Three places where I did.

### 2a · #50's example cost line is arithmetically wrong

The issue gives `gpt-4o-mini · 2,104 in / 61 out · 1.4s · $0.0006`. On the committed price
table 2,104 in / 61 out prices at **$0.000352**, not $0.0006. The example is illustrative; the
UI renders the computed figure. Nothing was copied from the ticket.

### 2b · #54's "5 clear the gate" and "13 at or above 0.70" are both true, of different things

`docs/eval/calibration_accuracy.json`: 90 measured, **13** have `accuracy >= 0.70`, but
`reportable_count` is **5** — because `reportable` tests the Wilson *lower bound* against 0.70,
not the point estimate. The issue's "5 clear the gate, 77 below it" mixes the two: 77 is
`accuracy < 0.70` (the point estimate), 5 is the bound. Both numbers are on the chart's note
with the distinction spelled out. Median 0.25, six at exactly 0.000, two unmeasured — all
confirmed.

### 2c · #54's three disagreement buckets are four, and the interesting one is worse than stated

The issue describes three buckets and puts "four of six" in the last. Recomputing each of the
six recorded decisions against MAUD gold (model prediction from `calibration_predictions.json`,
human label from the `labels` table, gold from `deal_points`):

| outcome | decisions |
|---|---|
| reviewer agreed with the model | 1 |
| reviewer corrected a wrong model answer | **0** |
| reviewer differed and overwrote an answer that was correct | 4 |
| reviewer differed, and was wrong either way | 1 |

**Not one of the six reviewer decisions matched the gold label**, and the "agreed" one agreed
with an answer that was itself wrong. The stacked bar carries the two non-empty outcomes in the
validated pair; the empty bucket is the finding, so it is stated in the copy and kept in the
table view rather than drawn as a zero-width segment nobody can see.

---

## 3 · Deviations from the issue text, with the reason

### 3a · Chart 1 is one hue, not a sequential ramp

#54 asks for "sequential blue by accuracy". The `dataviz` skill names that an anti-pattern:
a value-ramp on nominal categories re-encodes bar length as hue and spends the identity channel
on information the chart already shows. Deal points are nominal; the ranking is already carried
by sorting worst-first. So every bar takes categorical slot 1. Chart 4 is the same call.

**Cost accepted:** on a 1,793px scrolling chart, a ramp would give a coarse position cue while
scrolling that a single hue does not. The gate rule and the worst-first order have to carry
that instead.

### 3b · The corrections grade is a second endpoint, not a field on `/agent/grading`

#51 says "the grading panel on Ask shows both rows", and it does — but from two requests.
`backend/tests/test_grading.py` pins that `/agent/grading` grades with **no database**, by
monkeypatching `psycopg.connect` to raise for the duration of the call. Corrections live in
Postgres. Adding them to that endpoint would have cost the authored grade the one property
that lets a reader check it with nothing running, so `GET /agent/corrections-grade` serves
them instead.

**Cost accepted:** one more round trip on the Ask tab, and a panel that can render half its
table if the database is down. The half that survives is the authored one, which is the half
that never needed a database.

### 3c · Resolution covers industry labels only

#47 says filter values go through `resolve_filter_value`. That function's vocabulary is the
industry labels the corpus carries and nothing else, so a value on any other member passes
through marked `verbatim` and the chip says so.

**This is a real hole, and I left it open rather than widening the ladder in this issue.**
Observed on a live call: the model wrote `consideration_type = "cash"` where the corpus holds
`"All Cash"` — a filter that runs and returns zero rows, which reads as "we have no comparable
deals". The Ask tab prints exactly that example above the run button, so the risk is in front
of the reader, but a warning is not a fix. Closing it properly means resolving every filter
value against its own dimension's distinct values, which is a bigger change than #47 and would
have put a Cube query on a route whose stated property is that it never executes one.

### 3d · A string on a boolean dimension is refused — an addition, not in any issue

Asked "how many aerospace deals do we have", the model filtered
`comparable_deals.has_industry = "Aerospace"`. That dimension is a yes/no, so no row can hold
it: Cube returns zero rows, and zero rows read as "no comparable deals". Removing that
dimension from the model's choices just moved it to `is_inferred_industry` — it is matching the
substring "industry" in the name. Trimming the vocabulary chases that around, so instead the
route now refuses a value the dimension's own type cannot hold, with its reason and
`true`/`false` as the candidates. Cube's `/meta` supplies the types, so there is no second
hardcoded list of boolean dimensions to go stale.

---

## 4 · Database — action required at merge

**`selection_corrections` is NOT migrated into the shared `explorer` database**, per the work
order. `backend/explorer/db/schema.sql` carries it; `migrate.py`'s teardown list carries it;
the touch trigger is attached.

Proven on `explorer_47` (created for this by `pg_dump | psql` from `explorer`):

```
$ PYTHONPATH=backend CLAUSE_EXPLORER_DB=...explorer_47 python -m explorer.db.migrate up
{"tables": 6, "event": "migrate_up", ...}
$ psql -d explorer_47 -c "\d selection_corrections"
  ... 9 columns, PK, idx_selection_corrections_agreed,
  trigger trg_touch_selection_corrections BEFORE UPDATE
$ psql -d explorer_47 -c "SELECT count(*) FROM matters"
  152           # idempotent over existing data
```

**To migrate the shared one:**
`PYTHONPATH=backend python -m explorer.db.migrate up`

Until then, three DB-backed tests in `backend/tests/test_selection_corrections.py` **skip**
rather than fail, and Ask's corrections row renders "not measured". Against `explorer_47` all
ten pass.

`explorer_47` is mine and disposable — drop it whenever.

### One thing I changed in the shared database

The shared `explorer` had **153 matters**, not 152, which broke 11 tests at baseline. The extra
row was `refresh_probe_038c23b301d3` / "REFRESH PROBE INC." — the temp row inserted by
`test_cube_model.py::TestNewRowsAppearWithoutARestart`, whose own `finally` block deletes it.
A run killed inside its 120-second poll had left it behind (its `updated_at` was 16:47 UTC, ~4
hours before I started). I deleted it, which is what that test's cleanup would have done. That
restored the documented 152 and the baseline went green. It was neither a migration nor an
ingest.

---

## 5 · Palette validation output, pasted

The only categorical palette introduced is the pre-validated pair. Charts 1 and 4 are a single
series and take slot 1 alone.

```
$ node scripts/validate_palette.js "#2a78d6,#eb6834" --mode light --surface "#ffffff"
Palette (light, surface #ffffff, categorical): 2 slots
  [PASS] Lightness band         all 2 inside L 0.43–0.77
  [PASS] Chroma floor           all 2 >= 0.1
  [PASS] CVD separation         worst adjacent #eb6834↔#2a78d6 ΔE 24.7 (protan) · tritan 32.7
  [PASS] Normal-vision floor    worst adjacent #eb6834↔#2a78d6 ΔE 33.6 (normal)
  [PASS] Contrast vs surface    all 2 >= 3:1
  → ALL CHECKS PASS

$ node scripts/validate_palette.js "#3987e5,#d95926" --mode dark --surface "#1a1a19"
Palette (dark, surface #1a1a19, categorical): 2 slots
  [PASS] Lightness band         all 2 inside L 0.48–0.67
  [PASS] Chroma floor           all 2 >= 0.1
  [PASS] CVD separation         worst adjacent #d95926↔#3987e5 ΔE 26.8 (protan) · tritan 32.4
  [PASS] Normal-vision floor    worst adjacent #d95926↔#3987e5 ΔE 31.8 (normal)
  [PASS] Contrast vs surface    all 2 >= 3:1
  → ALL CHECKS PASS

slot 1 alone, contrast: 4.42:1 on #ffffff · 4.79:1 on #1a1a19
```

A four-hue set (`#2a78d6,#eb6834,#1baf7a,#eda100`) was validated too, in case the disagreement
chart needed four segments — it passes every hard check but WARNs on contrast for slots 3 and 4
(2.82 and 2.17), which obligates relief. Not used: two segments plus the table view says the
same thing with no warning to carry.

### A note on the dark values

`CLAUDE.md` says do not restore the dark palette, and the app ships light only. #54 requires
chart colours defined for light and dark under both the media query and the `data-theme` scope,
so `.viz` declares them in all three places.

**Cost accepted:** the dark branch is unreachable in the app as it stands — dead CSS today,
correct the moment a theme toggle exists. The alternative was leaving the charts to invert
wrongly under a future toggle.

---

## 6 · Smaller things a reviewer might ask about

- **`Admin.tsx` and `Admin.test.tsx` are deleted, not emptied.** Ingest status and the log
  viewer moved verbatim to `frontend/src/components/operator.tsx`; the calibration tables are
  superseded by Trust's charts, which read the same two artefacts.
- **`docs/results/measure-selection.json` is new and committed.** Written by
  `python -m explorer.evals --only measure-selection`, which previously wrote nothing. A test
  asserts the committed numbers still match what the harness computes, so a stale artefact
  fails the gate rather than quietly charting an old number.
- **`Vocabulary` gained `dimension_types`**, defaulted to `()`, so every existing caller and
  test constructs one unchanged. Types come from Cube's `/meta`.
- **`select_via_llm` is now a thin wrapper** over `select_with_usage`. The eval recorder is
  untouched.
- **The live `needs_key` Ask test does not assert the model selected well.** Across four probe
  calls the same question returned an empty selection once and the entire 11-measure,
  18-dimension vocabulary once. `measure_selection.json` already scores that judgement at 0.80
  measure precision and 0.20 refusal accuracy; asserting it here would be a flaky duplicate.
  The test asserts what the route owes: a selection came back, and it carries no figure.
- **The screenshot pass caught a real defect no unit test would have.** The loop diagram's new
  caption ("the score went DOWN") measured 98px at 9px italic against a middle anchor at x=46,
  so it ran off the viewBox to x=-3 and collided with "no API call". Shortened and moved into
  the clear band. Re-checked: no overflow, no collisions, no horizontal page scroll.

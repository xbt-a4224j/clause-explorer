# Merge notes — issues #38 and #9

Written because `README.md` is owned by another process in this cycle and must not be edited
here. Everything below is a README implication someone else has to land, plus the handful of
facts a reviewer of this branch will want.

## README implications

Nothing in the README is made *wrong* by this branch, but two things are now under-stated:

1. **Line ~144** already says the self-assigned SIC code "resolves 134 of 152". That number is
   confirmed against the live database (see `docs/provenance.md`, "Enrichment coverage"). No
   edit needed — recorded here so nobody "corrects" it.
2. **Deal value.** The architecture block near the top lists EDGAR as the source of
   "SIC industry · deal value · dates · parties". **Deal value is not populated — 0 of 152**,
   and cannot be from the endpoints this ingest uses. If the README is being revised anyway,
   that line should read `SIC industry · dates · parties` with deal value called out as not
   yet available. Leaving it as-is asserts a field the database does not have, which is the
   kind of claim CLAUDE.md's no-fabricated-numbers rule exists to prevent.
3. If a coverage table is ever wanted in the README, the measured one lives in
   `docs/provenance.md` under "Enrichment coverage (#9) — measured, not estimated". Copy it
   rather than recomputing from memory.

## What this branch changed

- `frontend/src/abort.ts` (new) — `isAbortError`, `ignoreAbort`, `useAbortOnUnmount`.
- Every fetching view/component now passes an `AbortSignal` and aborts on unmount:
  `App`, `Explore`, `Coverage`, `DealTerms`, `Tables`, `Admin` (4 effects), `Label`,
  `Overview`, `SemanticLayer`, `MatterCard`, `Grading`, `QueryBuilder`.
- `frontend/src/abortOnUnmount.test.tsx` (new) — 11 tests.
- `frontend/src/views/Explore.test.tsx`, `frontend/src/views/Label.test.tsx` — the actual
  cause of the flake, see below.
- `docs/provenance.md` — crosswalk coverage, measured enrichment coverage, corrected row count.

## Deliberately NOT changed

- `backend/explorer/ingest/edgar.py` — another agent holds it for #42. Job 2 was an audit of
  that file, not an edit to it. No gap found in it required a code change.
- `README.md` — see above.
- The `explorer` database — read-only throughout. No migration, no ingest, no writes.

## The flake was not the missing abort

#38's leading hypothesis was wrong, and the branch says so. The abort work is a real fix for a
real defect, but it did not stop the flake. The flake is reproducible on demand by saturating
the CPU (eight busy loops) while the suite runs, and it survived the AbortController change
unchanged — same two tests, same two files the issue named.

The actual cause is on the test side, and there are two of them:

- **`Explore.test.tsx`** awaited the facet rail's landmark and then reached for a facet button
  synchronously. The landmark renders before the facets arrive, so the button was legitimately
  absent. Fixed by awaiting the button.
- **`Label.test.tsx`** awaited the clause text and then pressed a key. `findBy*` resolves off a
  DOM mutation, which happens at commit; the passive effect that installs the `keydown`
  listener flushes afterwards. Under contention that gap widened past the keypress, so the key
  reached no handler — which is precisely the "fails in 36 ms, the state update genuinely did
  not happen" symptom in the issue. Fixed by flushing effects before the keypress.

Both were latent from the day they were written; parallel load only made the window wide
enough to hit. Neither is a product defect.

**A measurement caveat, recorded because it nearly produced a false result.** The first
"after" batch reported a failure on an ostensibly unloaded run. It was not unloaded: the
`kill $LOAD` in the throwaway load script used `jobs -p`, which does not enumerate background
jobs in a non-interactive zsh, so sixteen busy loops from two earlier invocations were still
running — load average 223 at the time the batch was recorded. Every number in that batch was
measured under conditions I did not intend and did not know about. The final measurements were
re-taken after killing the strays by PID, with the load phase kept separate and explicit. If
the run counts in the #38 comment look conservative, this is why.

## One judgement call worth reviewing

`Label`, `Tables` and two `Admin` effects previously had **no** `.catch` at all, so a failed
request surfaced as an unhandled rejection. Adding an abort-aware `.catch` there could have
quietly swallowed real failures, which would be a worse defect than the one being fixed. They
now re-throw anything that is not an `AbortError`, preserving the existing behaviour exactly
and narrowing the new `catch` to teardown only. Accepted cost: those views still have no
designed error state — that is pre-existing and out of scope for #38.

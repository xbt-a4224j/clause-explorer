# Calibration: extractor vs held-out MAUD labels (#28)

The generalization claim CLAUDE.md makes — usable on documents nobody annotated — is only
credible with a measured accuracy on a held-out slice. This is that measurement, and it is not
a flattering one for most of the deal points tested; recorded here as-is per the project's
no-fabricated-numbers rule.

**There is no production extraction pipeline in this app** — MAUD's own labels ARE the product
data (CLAUDE.md), loaded directly rather than re-extracted. The extractor calibrated here
(`backend/explorer/evals/extract_deal_point.py`) exists solely to produce this figure for a
*hypothetical* future extractor: a minimal GPT-4o-mini classifier, enum-constrained to each deal
point's own observed position vocabulary, given a truncated window of the raw contract.

## Held-out split

`docs/eval/calibration_split.json`, committed, not regenerated per run: 20 of 152 matters
(~13%), selected by `sha256(matter_id)` ascending — a deterministic method with no manual
curation, so it cannot have been chosen to look good.

## Deal points tested

5 deal points, chosen **before any prediction was run**, for having a small closed position
vocabulary (binary Y/N-style, answered on all 152 matters) — chosen off the full corpus's
position distribution, not the holdout's, so the holdout was never consulted during selection:

- `Announcement, pendency or consummation of deal (Y/N)`
- `"Ability to consummate" concept is subject to MAE carveouts`
- `Actions taken by Buyer-Answer (Y/N)`
- `Acquisition Proposal required to be publicly disclosed-Answer (Y/N)`
- `Action prohibited/omission required by the agreement-Answer`

This is 5 of 92 deal points, not full coverage — a slice, per CLAUDE.md's "run our extractor
over a held-out MAUD slice."

## Commands

```
$ PYTHONPATH=backend python -c "from explorer.evals.calibration import record_predictions; record_predictions()"
# writes docs/eval/calibration_predictions.json — 100 predictions (20 matters x 5 deal points)

$ PYTHONPATH=backend python -m explorer.evals.calibration
```

## Results

Recorded 2026-07-30 with `gpt-4o-mini`, `min_extraction_confidence = 0.7` (#23):

| deal point | n | correct | accuracy | 95% CI | reportable |
|---|---|---|---|---|---|
| Announcement, pendency or consummation of deal (Y/N) | 20 | 19 | 0.950 | [0.764, 0.991] | **yes** |
| Acquisition Proposal required to be publicly disclosed-Answer (Y/N) | 20 | 10 | 0.500 | [0.299, 0.701] | no |
| "Ability to consummate" concept is subject to MAE carveouts | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| Action prohibited/omission required by the agreement-Answer | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| Actions taken by Buyer-Answer (Y/N) | 20 | 4 | 0.200 | [0.081, 0.416] | no |

95% Wilson score interval (stable at small n, unlike the normal approximation, which can push a
bound outside [0, 1] exactly where these numbers sit). 4 of 5 deal points' lower CI bound falls
below the #23 threshold and are **not reportable** — the honest outcome the AC asks this table
to make explicit, not a target to hit.

## Human labels are read back into this score (#41)

The Label tab writes a row to `labels` for every decision. Since #41 the grader prefers that row
over the model's answer for the same `(matter_id, deal_point_name)` and then grades it against
MAUD exactly as it graded the model — a *substitution*, not a correction, so a bad label lowers
the number. The machine-readable artefact is `docs/results/calibration-labels.json`.

```
$ CLAUSE_EXPLORER_DB=postgresql://explorer:explorer@localhost:5432/explorer_41 \
    PYTHONPATH=backend python -m explorer.evals.calibration
```

Recorded 2026-09-04 against 6 decisions already sitting in `labels` — real keystrokes from the
Label tab, not seeded:

| deal point | n | correct before | correct after | labels applied |
|---|---|---|---|---|
| "Ability to consummate" concept is subject to MAE carveouts | 20 | 6 | 5 | 1 |
| Acquisition Proposal required to be publicly disclosed-Answer (Y/N) | 20 | 10 | 10 | 4 |
| Action prohibited/omission required by the agreement-Answer | 20 | 6 | 6 | 1 |
| Actions taken by Buyer-Answer (Y/N) | 20 | 4 | 4 | 0 |
| Announcement, pendency or consummation of deal (Y/N) | 20 | 19 | 19 | 0 |
| **all** | **100** | **45** | **44** | **6** |

`correct before` reproduces the table above exactly, which is the check that the change did not
quietly move the baseline.

**The number went down, and that is the mechanism working.** 6 labels were applied; 2 differed
from the model's answer. One of those two is `contract_25` / MAE carveouts, where gold is `No`,
the model said `No`, and the recorded label is `s` — a stray keystroke that turned a right answer
into a wrong one, costing exactly 1/20 on that deal point and 1/100 overall. The other,
`contract_143`, replaced a wrong `No` with an equally wrong `N` against a gold of `Yes`, and
moved nothing. A loop that could only report improvement would be a loop worth distrusting.

**What this does not show.** All 20 holdout matters already have a lawyer's answer in
`deal_points`, so a reviewer at the Label tab can at best reproduce gold and at worst, as here,
mistype it. Nothing was learned from this review that MAUD did not already contain. What the
closed loop buys is the mechanism for documents with *no* gold — firm precedents, where the
reviewer's decision is the only answer there is. The measurement above demonstrates the wiring,
not a benefit to this corpus.

## The finding: one deal point generalizes, four do not

`Announcement, pendency or consummation of deal (Y/N)` is a genuinely easy classification — its
answer is near-universal boilerplate stated early in most agreements, well within the 12,000-
character context window given to the model. The other four require reading specific covenant
language that is not reliably front-loaded in a merger agreement; truncating context to the
first 12,000 characters (a real, stated methodological limitation, not hidden) likely accounts
for a meaningful share of the misses, but truncation is not the only cause — several wrong
predictions had *located* quotes (the model found and cited real text) that supported the wrong
position given the deal point's precise legal definition. Distinguishing "Constructive
knowledge" from "Actual knowledge" — the exact pair #21's drill-through surfaced as a real,
subtle distinction between two real clauses — is exactly the kind of judgment this minimal
extractor was not built to make reliably.

## Cost

317,553 total tokens across 100 predictions (measured, from `response.usage.total_tokens`).
Input/output token counts were not captured separately, so cost is bounded rather than stated
as a false-precision point figure:

- gpt-4o-mini pricing read from https://developers.openai.com/api/docs/pricing on 2026-07-30:
  $0.15 / 1M input tokens, $0.60 / 1M output tokens.
- All-input bound: 317,553 / 1,000,000 × $0.15 = **$0.048**
- All-output bound: 317,553 / 1,000,000 × $0.60 = **$0.190**
- Actual cost sits toward the low end of that range: each call sends a ~3,000-token contract
  excerpt and returns a short JSON object (one enum value plus a quoted sentence), so input
  tokens dominate total tokens by a wide margin.

## This accuracy is known on this distribution, and is an assumption elsewhere

These numbers describe GPT-4o-mini's ability to classify five specific, easy-to-verify deal
points from public SEC merger agreements in the MAUD distribution, with a 12,000-character
context window and this exact prompt. They say nothing about:

- the other 87 deal points, several of which require judgment MAUD's own annotators needed
  training to apply consistently
- non-merger commercial contracts, a different document type entirely
- a different model, a longer context window, or a different prompt

Any of those is a new calibration run, not an extrapolation from this one.

## Not done

- Only 5 of 92 deal points calibrated — the ones with the simplest position vocabulary, which
  biases the sample toward the easy end of the task. A full-coverage run is a much larger,
  separate cost and time commitment than this issue's scope.
- No attempt to improve the extractor (larger context window, retrieval-anchored excerpts
  instead of a flat truncation, a stronger model) — #28 asks for the measurement, not a target
  accuracy, and CLAUDE.md is explicit that a worse-than-hoped number is the finding to record,
  not a bug to iterate away before publishing.

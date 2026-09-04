# Calibration: extractor vs held-out MAUD labels (#28, widened to all 92 deal points in #44)

The generalization claim CLAUDE.md makes — usable on documents nobody annotated — is only
credible with a measured accuracy on a held-out slice. This is that measurement, and it is not
a flattering one; recorded here as-is per the project's no-fabricated-numbers rule.

**There is no production extraction pipeline in this app** — MAUD's own labels ARE the product
data (CLAUDE.md), loaded directly rather than re-extracted. The extractor calibrated here
(`backend/explorer/evals/extract_deal_point.py`) exists solely to produce this figure for a
*hypothetical* future extractor: a minimal GPT-4o-mini classifier, constrained to each deal
point's own observed position vocabulary, given a truncated window of the raw contract.

#28 measured 5 deal points chosen by hand for having a small closed position vocabulary. That
is 5% of the label space, selected for being easy to grade, and it is why the headline "4 of 5
below the gate" was never a weakness map. #44 removes the hand-picked list: the vocabulary is
read from the data, and every deal point MAUD labelled on the holdout is measured.

## Held-out split

`docs/eval/calibration_split.json`, committed, not regenerated per run: 20 of 152 matters
(~13%), selected by `sha256(matter_id)` ascending — a deterministic method with no manual
curation, so it cannot have been chosen to look good.

## What was scheduled, and what landed

Only **labelled pairs** are scheduled. MAUD does not answer every deal point for every
agreement; predicting an unanswered pair would be graded against a label that does not exist,
which is a fabricated error rate paid for in real tokens.

- 1,704 (matter, deal point) pairs carry a MAUD label on the 20 holdout matters
- **1,701 predictions landed.** 3 were dropped after 6 attempts, all on
  `Accuracy of Fundamental Target R&Ws-Types of R&Ws` — the deal point with 73 distinct
  positions and by far the largest prompt. They are absent from that row's `n`, not counted as
  wrong.
- 90 of the 92 deal points are measured. The 2 unmeasured ones are a **coverage gap, not a
  failure**: MAUD answers them on no holdout matter, so this split cannot say anything about
  them. They render as "not measured", never as 0.00.

## Commands

```
$ PYTHONPATH=backend python -c "from explorer.evals.calibration import record_predictions; record_predictions()"
# writes docs/eval/calibration_predictions.json and docs/eval/calibration_cost.json

$ PYTHONPATH=backend python -c "from explorer.evals.calibration import record_predictions; record_predictions(resume=True, max_workers=4)"
# the resumed pass: only the pairs the first pass lost to rate limits

$ PYTHONPATH=backend python -m explorer.evals.calibration
# grades offline and writes docs/eval/calibration_accuracy.json
```

## Cost — measured, not estimated

From `docs/eval/calibration_cost.json`, summed from each call's own `response.usage`:

| | |
|---|---|
| calls | 1,701 |
| input tokens | 5,440,750 |
| output tokens | 63,882 |
| **total cost** | **$0.854442** |
| cost per call | $0.00050232 |
| model | `gpt-4o-mini` |

Priced at $0.15 / 1M input and $0.60 / 1M output, read from
https://developers.openai.com/api/docs/pricing on 2026-09-03 and committed in
`backend/explorer/evals/pricing.py` with that date.

Input and output are counted separately, which #28 could not do: it recorded only
`total_tokens`, so it had to publish a range ($0.048–$0.190) instead of a figure. gpt-4o-mini
charges 4x for output, so a total-token count cannot be priced.

The run was authorised by measuring **one** call first — 3,064 input + 117 output tokens =
$0.0005298 — and multiplying by the 1,704 scheduled pairs for an extrapolation of $0.90. The
actual total came in at $0.854442.

## Results — all 92 deal points, worst first

`n` is that deal point's own held-out sample; it is not 20 everywhere, because MAUD does not
answer every deal point on every matter. "clears 0.70" is the **lower** bound of the 95% Wilson
interval against `min_extraction_confidence`, not the point estimate — 3 of 4 correct reads as
0.75 but its interval reaches 0.30, and a sample too small to distinguish the extractor from a
coin flip must not clear the gate.

`correct` is the **graded** answer, which means a human label from the Label tab where one
exists (#41) and the model's prediction everywhere else. Six pairs across three deal points
carry a label; the extractor-only figures and what the labels cost are in the next section. The
gate reads this column, so it is the one that has to include them.

| deal point | n | correct | accuracy | 95% CI | clears 0.70 |
|---|---|---|---|---|---|
| Accuracy of Fundamental Target R&Ws-Types of R&Ws | 17 | 0 | 0.000 | [0.000, 0.184] | no |
| COR standard (board determination only)-answer | 2 | 0 | 0.000 | [0.000, 0.658] | no |
| Definition includes stock deals-Answer | 19 | 0 | 0.000 | [0.000, 0.168] | no |
| Initial matching rights period (FTR)-Answer | 16 | 0 | 0.000 | [0.000, 0.194] | no |
| Tail Period Length-Answer | 20 | 0 | 0.000 | [0.000, 0.161] | no |
| W/N/A/F applies to-Answer | 20 | 0 | 0.000 | [0.000, 0.161] | no |
| Acquisition Proposal Timing-Answer | 20 | 1 | 0.050 | [0.009, 0.236] | no |
| Change in Target's industry: subject to "disproportionate impact" modifier | 20 | 1 | 0.050 | [0.009, 0.236] | no |
| General political and/or social conditions:  subject to "disproportionate impact" modifier | 20 | 1 | 0.050 | [0.009, 0.236] | no |
| Initial matching rights period (COR)-Answer | 20 | 1 | 0.050 | [0.009, 0.236] | no |
| Specific Performance-Answer | 20 | 1 | 0.050 | [0.009, 0.236] | no |
| W/N/A/F subject to "disproportionate impact"-Answer | 20 | 1 | 0.050 | [0.009, 0.236] | no |
| Definition contains knowledge requirement - answer | 18 | 1 | 0.056 | [0.010, 0.258] | no |
| Acquisition Proposal required to be publicly disclosed-Answer | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Additional matching rights period for modifications (COR)-Answer | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Changes in Target's industry (Y/N) | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| FLS (MAE) Standard-Answer | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| General political and/or social conditions (Y/N) | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Number of additional matching rights periods for modifications (COR) | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Pandemic or other public health event:  subject to "disproportionate impact" modifier | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Pandemic or other public health event: Specific reference to COVID-19 | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Relational language (MAE carveout)-Answer (Dropdown) | 20 | 2 | 0.100 | [0.028, 0.301] | no |
| Number of additional matching rights periods for modifications (FTR) | 16 | 2 | 0.125 | [0.035, 0.360] | no |
| Breach of No Shop required to be willful, material and/or intentional | 7 | 1 | 0.143 | [0.026, 0.513] | no |
| Accuracy of Target Capitalization R&W (outstanding shares): Bringdown Standard Answer | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Application of Buyer consent requirement (negative interim covenant)-Answer | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| COR permitted with board fiduciary determination only | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Change in law:  subject to "disproportionate impact" modifier | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Changes in GAAP or other accounting principles (Y/N) | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Changes in market price/trading volume of Target's securities or credit rating (Y/N) | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Fiduciary exception:  Board determination standard-Answer (no-shop) | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Pandemic or other public health event-Answer (Y/N) | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| War, terrorism, natural disasters, "acts of God" or force majeure-Answer (Y/N) | 20 | 3 | 0.150 | [0.052, 0.360] | no |
| Definition includes asset deals-Answer | 19 | 3 | 0.158 | [0.055, 0.376] | no |
| Limitations on FTR Exercise-Answer | 16 | 3 | 0.188 | [0.066, 0.430] | no |
| "Ability to consummate" concept is subject to MAE carveouts | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| A/P/C application to-Answer | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| COR permitted in response to Intervening Event | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| COR standard (superior offer) | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| Changes in GAAP or other accounting principles:  subject to "disproportionate impact" modifier | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| FLS (MAE) applies to | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| General economic and financial conditions: subject to "disproportionate impact" modifier | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| Ordinary course efforts standard-Answer | 20 | 4 | 0.200 | [0.081, 0.416] | no |
| Action prohibited/omission required by the agreement-Answer | 20 | 5 | 0.250 | [0.112, 0.469] | no |
| Failure to meet projections (Y/N) | 20 | 5 | 0.250 | [0.112, 0.469] | no |
| Includes "consistent with past practice" | 20 | 5 | 0.250 | [0.112, 0.469] | no |
| Relational language (MAE carveout)-Answer (Y/N) | 20 | 5 | 0.250 | [0.112, 0.469] | no |
| Materiality/MAE Scrape applies to | 19 | 5 | 0.263 | [0.118, 0.488] | no |
| Intervening Event - Required to Occur After Signing - answer | 18 | 5 | 0.278 | [0.125, 0.509] | no |
| Accuracy of Target "General" R&W: Bringdown Timing Answer | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| Change in law (Y/N) | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| General Antitrust Efforts Standard-Answer | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| MAE Forward looking standard (Y/N) | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| Matters listed on disclosure schedules-Answer (Y/N) | 20 | 6 | 0.300 | [0.145, 0.519] | no |
| Breach of Meeting Covenant required to be willful, material and/or intentional | 3 | 1 | 0.333 | [0.061, 0.792] | no |
| Definition contains a materiality standard (Y/N) | 18 | 6 | 0.333 | [0.163, 0.563] | no |
| Knowledge persons include Target management (intervening event) | 18 | 6 | 0.333 | [0.163, 0.563] | no |
| Accuracy of Target "General" R&W: Bringdown Standard Answer | 20 | 7 | 0.350 | [0.181, 0.567] | no |
| Actions taken by Buyer-Answer (Y/N) | 20 | 7 | 0.350 | [0.181, 0.567] | no |
| COR standard (intervening event) | 20 | 7 | 0.350 | [0.181, 0.567] | no |
| Relational language (MAE) applies to | 20 | 7 | 0.350 | [0.181, 0.567] | no |
| Target stockholder proceedings-Answer (Y/N) | 20 | 7 | 0.350 | [0.181, 0.567] | no |
| General economic and financial conditions (Y/N) | 20 | 8 | 0.400 | [0.219, 0.613] | no |
| Liability for breaches of no-shop by Target Representatives (Y/N) | 20 | 8 | 0.400 | [0.219, 0.613] | no |
| Additional matching rights period for modifications (FTR)-Answer | 14 | 6 | 0.429 | [0.214, 0.674] | no |
| Knowledge Definition-Answer | 20 | 9 | 0.450 | [0.258, 0.658] | no |
| MAE definition includes adverse impact on Target's ability to consummate (Y/N) | 20 | 9 | 0.450 | [0.258, 0.658] | no |
| Liability standard for no-shop breach by Target Non-D&O Representatives | 19 | 9 | 0.474 | [0.273, 0.683] | no |
| Acquisition Proposal required to be publicly disclosed-Answer (Y/N) | 20 | 10 | 0.500 | [0.299, 0.701] | no |
| Failure to meet projections: subject to "disproportionate impact" modifier | 20 | 10 | 0.500 | [0.299, 0.701] | no |
| Negative Interim Covenant includes carveout for pandemic responses-Answer (Y/N) | 20 | 11 | 0.550 | [0.342, 0.742] | no |
| Type of Consideration-Answer | 20 | 11 | 0.550 | [0.342, 0.742] | no |
| FTR Triggers-Answer | 16 | 9 | 0.562 | [0.332, 0.769] | no |
| Acquisition Proposal required to be still pending-Answer (Y/N) | 20 | 12 | 0.600 | [0.387, 0.781] | no |
| Pandemic or other public health event: specific reference to pandemic-related governmental responses or measures | 20 | 12 | 0.600 | [0.387, 0.781] | no |
| Accuracy of Fundamental Target R&Ws: Bringdown Standard | 20 | 13 | 0.650 | [0.433, 0.819] | no |
| Knowledge Definition limited to one or more identified persons-Answer (Y/ | 20 | 13 | 0.650 | [0.433, 0.819] | no |
| Actions taken with consent or approval of Buyer-Answer (Y/N) | 20 | 14 | 0.700 | [0.481, 0.855] | no |
| Ordinary Course Covenant includes carve-out for Pandemic responses-Answer (Y/N) | 20 | 14 | 0.700 | [0.481, 0.855] | no |
| "Financial point of view" is the sole consideration | 15 | 12 | 0.800 | [0.548, 0.930] | no |
| Fiduciary exception: Board determination trigger (no shop)-Answer | 20 | 16 | 0.800 | [0.584, 0.919] | no |
| Buyer consent requirement (ordinary course)-Answer | 20 | 17 | 0.850 | [0.640, 0.948] | no |
| Compliance with Target Covenant Closing Condition-Answer | 20 | 18 | 0.900 | [0.699, 0.972] | no |
| MAE definition includes reference to Target "prospects" (Y/N) | 20 | 18 | 0.900 | [0.699, 0.972] | no |
| Constructive Knowledge-Answer | 11 | 10 | 0.909 | [0.623, 0.984] | no |
| Actions required under transaction agreement-Answer (Y/N) | 20 | 19 | 0.950 | [0.764, 0.991] | **yes** |
| Announcement, pendency or consummation of deal (Y/N) | 20 | 19 | 0.950 | [0.764, 0.991] | **yes** |
| Buyer consent requirement (negative interim covenant)-Answer | 20 | 19 | 0.950 | [0.764, 0.991] | **yes** |
| MAE applies to Target and subsidiaries (MAE)-Answer | 20 | 19 | 0.950 | [0.764, 0.991] | **yes** |
| Target's securities or credit rating: subject to "disproportionate impact" modifier | 20 | 19 | 0.950 | [0.764, 0.991] | **yes** |
| Absence of Litigation Closing Condition: Governmental v. Non-Governmental-Answer | 0 | — | not measured | — | — |
| Absence of Litigation Closing Condition: Pending v. Threatened v. Threatened in Writing-Answer | 0 | — | not measured | — | — |

threshold=0.7
accuracy point-estimate >= threshold: 13
ci_low >= threshold (reportable): 5
worst: Accuracy of Fundamental Target R&Ws-Types of R&Ws 0.0
best: Actions required under transaction agreement-Answer (Y/N) 0.95

## Human labels are read back into this score (#41)

The Label tab writes a row to `labels` for every decision. Since #41 the grader prefers that row
over the model's answer for the same `(matter_id, deal_point_name)` and then grades it against
MAUD exactly as it graded the model — a *substitution*, not a correction, so a bad label lowers
the number. The machine-readable artefact is `docs/results/calibration-labels.json`.

```
$ PYTHONPATH=backend python -m explorer.evals.calibration
correct 569 of 1701 before, 565 of 1701 after; 6 labels applied, 5 differing
```

Regenerated 2026-09-04 against the #44 predictions file. #41 measured this on #28's 100
predictions and recorded 45 before / 44 after; #44 then replaced that file with 1,701
predictions from a changed answer channel, so those figures described nothing on disk and the
numbers below replace them. The 6 decisions in `labels` are unchanged — real keystrokes from the
Label tab, not seeded.

| deal point | n | correct before | correct after | labels applied |
|---|---|---|---|---|
| "Ability to consummate" concept is subject to MAE carveouts | 20 | 4 | 4 | 1 |
| Acquisition Proposal required to be publicly disclosed-Answer (Y/N) | 20 | 13 | 10 | 4 |
| Action prohibited/omission required by the agreement-Answer | 20 | 6 | 5 | 1 |
| **all 90 measured deal points** | **1,701** | **569** | **565** | **6** |

Accuracy 0.335 before, 0.332 after: **−4 correct answers on a denominator seventeen times
larger than #41 measured on.** The delta is negative, and it is larger in absolute terms than it
was at n=100.

**The number went down, and that is the mechanism working.** All 6 labels were applied and 5 of
them differ from the model's answer. On the wider run the extractor happened to be *right* on
four of the six pairs a reviewer touched, and every one of those four labels is wrong against
MAUD:

| matter | deal point | gold | model | label | effect |
|---|---|---|---|---|---|
| contract_10 | Acquisition Proposal required to be publicly disclosed | Yes | Yes | `No` | right → wrong |
| contract_143 | Acquisition Proposal required to be publicly disclosed | Yes | Yes | `N` | right → wrong |
| contract_143 | Action prohibited/omission required by the agreement | Yes | Yes | `No` | right → wrong |
| contract_150 | Acquisition Proposal required to be publicly disclosed | Yes | Yes | `No` | right → wrong |
| contract_25 | "Ability to consummate" subject to MAE carveouts | No | Yes | `s` | wrong → wrong |
| contract_25 | Acquisition Proposal required to be publicly disclosed | Yes | No | `No` | wrong → wrong |

`s` is a stray keystroke. `N` is a half-typed `No`. The three `No`s contradict MAUD's `Yes`.
These were exercise decisions made to prove the Label tab wrote rows, not a review anyone stands
behind — and the grader is not permitted to know the difference. A loop that could only report
improvement would be a loop worth distrusting; this one reports the loss.

**What this does not show.** All 20 holdout matters already have a lawyer's answer in
`deal_points`, so a reviewer at the Label tab can at best reproduce gold and at worst, as here,
mistype it. Nothing was learned from this review that MAUD did not already contain. What the
closed loop buys is the mechanism for documents with *no* gold — firm precedents, where the
reviewer's decision is the only answer there is. The measurement above demonstrates the wiring,
and demonstrates that it can report a loss; it is not evidence that human review helps this
corpus.

## The finding: the extractor is not usable on un-annotated documents

Of the 90 deal points measured:

- **5 clear the 0.70 gate** on the lower CI bound. All five sit at 19 of 20 correct.
- 13 have a point-estimate accuracy at or above 0.70; the other 8 of those have intervals too
  wide to clear it, which is the gate working as intended rather than a rounding quarrel.
- **77 of 90 are below 0.70** on the point estimate. The median accuracy across measured deal
  points is **0.25**.
- 6 deal points score **0.000** — the extractor got none of them right.

The 5 that clear are the same kind of question: near-binary, answered by boilerplate stated
early in a merger agreement. What fails is everything requiring the graded legal judgment MAUD's
own annotators needed training to apply — distinguishing "Constructive knowledge" from "Actual
knowledge", or picking one of 73 combinations of fundamental representations.

Two causes, and it matters which is which:

1. **Context truncation.** The extractor sends the first 12,000 characters. A deal point whose
   answer lives past that window is not being fairly evaluated. This is a limitation of the
   harness, and it is fixable.
2. **Judgment.** Several wrong predictions had *located* quotes — the model found and cited real
   contract text — that supported the wrong position given the deal point's precise definition.
   That is not fixable by a longer window.

This measurement does not separate the two. Doing so is a different experiment.

## What this changes downstream

- `deal_terms.confidence_lookup()` now reads `docs/eval/calibration_accuracy.json` instead of
  returning `None` for everything. The gate finally has data.
- **It still does not fire on anything the product serves.** Every one of the 12,937
  `deal_points` rows is a MAUD lawyer annotation (`is_inferred = false` on all of them). The
  extraction-confidence gate exists for extractor output only. Wiring a 0.25-median extractor
  accuracy into a rollup over lawyer-labelled data would suppress most of the product's own gold
  data on the strength of a number that describes something else — see
  `ROLLUP_IS_GOLD_LABELLED` in `backend/explorer/api/deal_terms.py` and the test that pins it.
- The Label queue draws from the full prediction set: **1,701 items across 90 deal points**, up
  from 100 across 5.

## This accuracy is known on this distribution, and is an assumption elsewhere

These numbers describe GPT-4o-mini classifying ABA deal points from public SEC merger agreements
in the MAUD distribution, with a 12,000-character context window and this exact prompt. They say
nothing about non-merger commercial contracts, a different model, a longer
context window, or a different prompt. Any of those is a new calibration run, not an
extrapolation from this one.

## Not done

- **The two unmeasured deal points stay unmeasured** on this split. Measuring them needs a
  different holdout, which would break the "held out means held out" property of the committed
  one.
- **No attempt to improve the extractor.** Longer context, retrieval-anchored excerpts instead
  of a flat truncation, a stronger model — all plausible, none tried. #28 and #44 ask for the
  measurement; CLAUDE.md is explicit that a worse-than-hoped number is the finding to record,
  not a bug to iterate away before publishing.
- **The 3 dropped calls were not retried a seventh time.** At n=17 instead of n=20 on one deal
  point already scoring 0.000, they cannot change a conclusion.

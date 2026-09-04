# Span anchoring: measured hit rate (#43)

MAUD records **where in the agreement an answer was found**, not the clause that carries it. This is the measured result of replacing each recorded span with the annotator's own quoted text where that text can be located inside it. An excerpt that appears more than once in the span is a **miss**, never a guess: storing the first occurrence would be an offset that opens the wrong clause and looks entirely right.

## Command

```
$ PYTHONPATH=backend python -m explorer.evals.span_anchoring \
      > docs/results/span-anchoring.md
```

## Overall

**7,476 of 12,937 deal points anchored — 57.8%.**

| | rows | anchored | rate |
|---|---:|---:|---:|
| all deal points | 12,937 | 7,476 | 57.8% |
| with a recorded span | 12,442 | 7,476 | 60.1% |
| with no span at all | 495 | 0 | 0.0% |

The 495 span-less rows were searched against the **whole document** under the same rules, and 0 were recovered. That is not a surprise in hindsight: a row has no span precisely because its quoted text could not be found in the file, and widening the search does not make absent text present.

## Why the misses missed

| outcome | rows | share |
|---|---:|---:|
| anchored | 7,476 | 57.8% |
| discontinuous excerpt | 4,766 | 36.8% |
| excerpt too short to anchor | 0 | 0.0% |
| quoted text not found in the span | 695 | 5.4% |
| quoted text appears more than once in the span | 0 | 0.0% |

The ambiguity rule never fired on this corpus — MAUD's quotations are long enough that none of them occurs twice inside its own span. It is a guard proven by fixture tests (`backend/tests/test_span_anchor.py`), not by a corpus row, and it stays because the cost of the alternative is a plausible-looking wrong offset.

The dominant miss is structural, not a matcher weakness: MAUD joins separate provisions with `<omitted>`, and several provisions are not one clause. Anchoring to one of them would present part of the basis for the answer as the whole of it, so those rows keep the recorded envelope and the drill-through keeps labelling them as excerpts.

## What this did to the stored spans

| | width (characters) | over `max_clause_chars` |
|---|---|---:|
| recorded, before #43 | median 4,658 · p90 238,949 · max 739,709 | 3,992 |
| stored, after #43 | median 4,658 · p90 238,949 · max 739,709 | 3,992 |
| the anchored rows alone | median 3,963 · p90 5,540 · max 8,707 | 321 |

**0 of the 7,476 anchored rows came out narrower than the span they replaced; 7,476 are byte-identical to it.** That is the finding, and it is not the one the ticket expected: the recorded span was never a loose region around the answer. Where MAUD quotes one continuous passage, the pre-existing locator already bounded exactly that passage, so there is nothing left to tighten. Where MAUD quotes several passages, the span is wide because the annotation itself is discontinuous — the width is a property of the annotation, not of our matching, and no matcher can remove it.

`max_clause_chars` is 6,000, so the drill-through's rendering is unchanged by this work: the same rows render as clauses and the same rows render as labelled excerpts. What anchoring adds is a claim the schema could not previously make — for an `anchored` row, the characters at this span are the text the annotator quoted and nothing else, verified per row; a `recorded` row is only *where the answer was found*.

## Alternatives tried

| matcher | anchored | rate | why not |
|---|---:|---:|---|
| whitespace collapse only | 4,176 | 32.3% | kept, but as the floor: page-break rules inside a quoted passage break an otherwise exact match |
| **+ page-rule deletion (shipped)** | 7,476 | 57.8% | a run of underscores or dashes is typographic furniture; deleting it cannot change what the text says |
| + head/tail anchors | 8,007 | 61.9% | **rejected.** It anchors on the first and last 120 characters and takes the interior on trust, so the span could no longer claim to be the quotation. It also bought nothing a reader would see: those rows are single-quotation rows whose recorded span was already clause-scale |

Quote and dash folding (curly to straight) was also measured and made **no difference at all** — MAUD's excerpts preserve the source's own punctuation — so it is not in the shipped matcher and not in this table.

## Per deal point

| deal point | n | anchored | rate |
|---|---:|---:|---:|
| Knowledge Definition limited to one or more identified persons-Answer (Y/ | 152 | 140 | 92% |
| Knowledge Definition-Answer | 152 | 140 | 92% |
| Constructive Knowledge-Answer | 84 | 77 | 92% |
| Definition contains a materiality standard (Y/N) | 128 | 115 | 90% |
| Definition contains knowledge requirement - answer | 128 | 115 | 90% |
| Intervening Event - Required to Occur After Signing - answer | 128 | 115 | 90% |
| Knowledge persons include Target management (intervening event) | 128 | 115 | 90% |
| "Ability to consummate" concept is subject to MAE carveouts | 152 | 134 | 88% |
| A/P/C application to-Answer | 152 | 134 | 88% |
| Action prohibited/omission required by the agreement-Answer | 152 | 134 | 88% |
| Actions required under transaction agreement-Answer (Y/N) | 152 | 134 | 88% |
| Actions taken by Buyer-Answer (Y/N) | 152 | 134 | 88% |
| Actions taken with consent or approval of Buyer-Answer (Y/N) | 152 | 134 | 88% |
| Announcement, pendency or consummation of deal (Y/N) | 152 | 134 | 88% |
| Change in Target's industry: subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| Change in law (Y/N) | 152 | 134 | 88% |
| Change in law:  subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| Changes in GAAP or other accounting principles (Y/N) | 152 | 134 | 88% |
| Changes in GAAP or other accounting principles:  subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| Changes in Target's industry (Y/N) | 152 | 134 | 88% |
| Changes in market price/trading volume of Target's securities or credit rating (Y/N) | 152 | 134 | 88% |
| FLS (MAE) Standard-Answer | 152 | 134 | 88% |
| FLS (MAE) applies to | 152 | 134 | 88% |
| Failure to meet projections (Y/N) | 152 | 134 | 88% |
| Failure to meet projections: subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| General economic and financial conditions (Y/N) | 152 | 134 | 88% |
| General economic and financial conditions: subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| General political and/or social conditions (Y/N) | 152 | 134 | 88% |
| General political and/or social conditions:  subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| MAE Forward looking standard (Y/N) | 152 | 134 | 88% |
| MAE applies to Target and subsidiaries (MAE)-Answer | 152 | 134 | 88% |
| MAE definition includes adverse impact on Target's ability to consummate (Y/N) | 152 | 134 | 88% |
| MAE definition includes reference to Target "prospects" (Y/N) | 152 | 134 | 88% |
| Matters listed on disclosure schedules-Answer (Y/N) | 152 | 134 | 88% |
| Pandemic or other public health event-Answer (Y/N) | 152 | 134 | 88% |
| Pandemic or other public health event:  subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| Pandemic or other public health event: Specific reference to COVID-19 | 152 | 134 | 88% |
| Pandemic or other public health event: specific reference to pandemic-related governmental responses or measures | 152 | 134 | 88% |
| Relational language (MAE carveout)-Answer (Dropdown) | 152 | 134 | 88% |
| Relational language (MAE carveout)-Answer (Y/N) | 152 | 134 | 88% |
| Relational language (MAE) applies to | 152 | 134 | 88% |
| Target stockholder proceedings-Answer (Y/N) | 152 | 134 | 88% |
| Target's securities or credit rating: subject to "disproportionate impact" modifier | 152 | 134 | 88% |
| W/N/A/F applies to-Answer | 152 | 134 | 88% |
| W/N/A/F subject to "disproportionate impact"-Answer | 152 | 134 | 88% |
| War, terrorism, natural disasters, "acts of God" or force majeure-Answer (Y/N) | 152 | 134 | 88% |
| Specific Performance-Answer | 149 | 118 | 79% |
| General Antitrust Efforts Standard-Answer | 152 | 100 | 66% |
| Definition includes stock deals-Answer | 146 | 91 | 62% |
| Definition includes asset deals-Answer | 145 | 90 | 62% |
| Buyer consent requirement (ordinary course)-Answer | 152 | 93 | 61% |
| Includes "consistent with past practice" | 152 | 93 | 61% |
| Ordinary Course Covenant includes carve-out for Pandemic responses-Answer (Y/N) | 152 | 93 | 61% |
| Ordinary course efforts standard-Answer | 152 | 93 | 61% |
| "Financial point of view" is the sole consideration | 120 | 70 | 58% |
| Application of Buyer consent requirement (negative interim covenant)-Answer | 152 | 88 | 58% |
| Buyer consent requirement (negative interim covenant)-Answer | 152 | 88 | 58% |
| Negative Interim Covenant includes carveout for pandemic responses-Answer (Y/N) | 152 | 88 | 58% |
| Type of Consideration-Answer | 152 | 77 | 51% |
| Liability standard for no-shop breach by Target Non-D&O Representatives | 138 | 66 | 48% |
| Liability for breaches of no-shop by Target Representatives (Y/N) | 152 | 69 | 45% |
| Compliance with Target Covenant Closing Condition-Answer | 152 | 11 | 7% |
| Additional matching rights period for modifications (FTR)-Answer | 122 | 6 | 5% |
| FTR Triggers-Answer | 129 | 6 | 5% |
| Initial matching rights period (FTR)-Answer | 129 | 6 | 5% |
| Number of additional matching rights periods for modifications (FTR) | 129 | 6 | 5% |
| Fiduciary exception:  Board determination standard-Answer (no-shop) | 151 | 7 | 5% |
| Fiduciary exception: Board determination trigger (no shop)-Answer | 151 | 7 | 5% |
| Tail Period Length-Answer | 151 | 6 | 4% |
| Acquisition Proposal Timing-Answer | 152 | 6 | 4% |
| Acquisition Proposal required to be publicly disclosed-Answer | 152 | 6 | 4% |
| Acquisition Proposal required to be publicly disclosed-Answer (Y/N) | 152 | 6 | 4% |
| Acquisition Proposal required to be still pending-Answer (Y/N) | 152 | 6 | 4% |
| Additional matching rights period for modifications (COR)-Answer | 148 | 5 | 3% |
| Initial matching rights period (COR)-Answer | 148 | 5 | 3% |
| Number of additional matching rights periods for modifications (COR) | 148 | 5 | 3% |
| COR permitted in response to Intervening Event | 152 | 4 | 3% |
| COR permitted with board fiduciary determination only | 152 | 4 | 3% |
| COR standard (superior offer) | 152 | 4 | 3% |
| COR standard (intervening event) | 139 | 3 | 2% |
| Limitations on FTR Exercise-Answer | 126 | 1 | 1% |
| Materiality/MAE Scrape applies to | 140 | 1 | 1% |
| Accuracy of Fundamental Target R&Ws-Types of R&Ws | 148 | 1 | 1% |
| Accuracy of Fundamental Target R&Ws: Bringdown Standard | 148 | 1 | 1% |
| Accuracy of Target "General" R&W: Bringdown Standard Answer | 150 | 1 | 1% |
| Accuracy of Target "General" R&W: Bringdown Timing Answer | 151 | 1 | 1% |
| Accuracy of Target Capitalization R&W (outstanding shares): Bringdown Standard Answer | 152 | 1 | 1% |
| Absence of Litigation Closing Condition: Governmental v. Non-Governmental-Answer | 13 | 0 | 0% |
| Absence of Litigation Closing Condition: Pending v. Threatened v. Threatened in Writing-Answer | 13 | 0 | 0% |
| Breach of Meeting Covenant required to be willful, material and/or intentional | 20 | 0 | 0% |
| Breach of No Shop required to be willful, material and/or intentional | 59 | 0 | 0% |
| COR standard (board determination only)-answer | 10 | 0 | 0% |

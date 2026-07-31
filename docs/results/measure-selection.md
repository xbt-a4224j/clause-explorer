# Measure-selection eval (#27)

25 authored question → expected-selection pairs (`docs/eval/measure_selection.json`), graded
offline against real recorded model output (`docs/eval/recorded_outputs.json`) — no database, no
LLM call, no network at grading time.

Recorded with `gpt-4o-mini` on 2026-07-30, after excluding the do-not-use-for-market measure
from the agent's selectable vocabulary (see "One fix made" below):

```
$ PYTHONPATH=backend python -m explorer.evals.record_measure_selection   # writes recorded_outputs.json
$ PYTHONPATH=backend python -m explorer.evals.measure_selection
{'case_count': 25, 'answerable_count': 20, 'refusal_count': 5,
 'measure_precision': 0.8, 'measure_recall': 0.775,
 'dimension_precision': 0.692, 'dimension_recall': 0.725,
 'filter_exact_match_rate': 0.5, 'refusal_accuracy': 0.2}
```

**Re-running the recorder against the live model reproduces slightly different numbers each
time** — this run's are not bit-identical to the run one commit prior (measure precision moved
0.817 → 0.8, filter exact-match 0.45 → 0.5). Same prompt, same questions, non-deterministic
model output. The committed `recorded_outputs.json` is what the numbers above are graded from,
so the report is reproducible from what's in the repo even though a fresh recording would drift.

## Aggregate

| metric | value | n |
|---|---|---|
| measure precision | 0.800 | 20 answerable cases |
| measure recall | 0.775 | 20 answerable cases |
| dimension precision | 0.692 | 20 answerable cases |
| dimension recall | 0.725 | 20 answerable cases |
| filter exact-match rate | 0.500 | 20 answerable cases |
| refusal accuracy | **0.200** | 5 refusal cases |

Answerable and refusal cases are scored separately — folding a "correctly declines" case into
the same precision/recall as an ordinary case would hide the actual finding here, which is in
the refusal column.

## The finding: refusal accuracy is the weak point, not measure selection

The model answered when it should have declined in 4 of 5 refusal cases:

| case | question | should refuse | did refuse | what it did instead |
|---|---|---|---|---|
| q21 | firm's win rate against Kirkland & Ellis | yes | **no** | filtered `acquirer_name = "Kirkland & Ellis"` — treated the counterparty field as opposing counsel |
| q22 | full text of a specific merger agreement | yes | yes | correctly emitted an empty selection |
| q23 | forecast next year's deal volume | yes | **no** | selected a count with a year time dimension — invented an answerable-looking query for an unanswerable one |
| q24 | deals originated by partner Jane Smith | yes | **no** | filtered `target_name = "Jane Smith"` — mapped a person's name onto the target-company field |
| q25 | average reverse termination fee | yes | **no**, but improved | selected `deal_points.median_numeric_value` — see below |

q21 and q24 are the sharpest results: the model does not recognize "the deal's counterparty" and
"who negotiated it" as outside the schema — it silently reinterprets the question to fit a field
that exists, rather than declining. That silent reinterpretation is precisely the risk #26's
resolved-query line exists to catch downstream, but the ideal is for the agent not to produce it
in the first place.

## One fix made: the do-not-use-for-market measure is now structurally excluded

The model file names `deal_points.mean_numeric_value_do_not_use_for_market` that way
specifically so a reader would not reach for it casually. The first recording showed the enum
still made it selectable regardless of the name: asked for "the average reverse termination
fee," the model picked exactly that measure — the trap the name exists to prevent, triggered on
the first live run of this eval.

Fixed by excluding it from `fetch_vocabulary()`'s output entirely (`agent/select.py`,
`EXCLUDED_MEASURES`) rather than trusting the name to be read as a warning — an enum that lists
a name makes it selectable no matter what the name says. Re-recorded after the fix: q25 now
selects `deal_points.median_numeric_value`, the correct measure for the question actually asked.

This does not move `refusal_accuracy` — the case still expects a refusal, and the model still
answers rather than declining — but it is a real quality improvement the binary refusal metric
doesn't credit: the model went from *confidently wrong* (a fabricated mean, an untraceable
number) to *confidently right* (the correct governed measure, just for a question that arguably
should have been declined rather than silently reinterpreted as "give me a number"). Worth
naming as a limitation of `should_refuse` as an operational definition: it does not distinguish
"answered with a defensible number" from "answered with a wrong one."

## Filter exact-match: the same industry-dimension confusion #25 exists to catch

The dominant failure pattern (q05, q06, q14, q20) is the model filtering on
`comparable_deals.has_industry` — a boolean "is this matter classified at all" dimension — with
a *value* like `"Healthcare"`, instead of filtering `comparable_deals.label = "Health Care
Industry"`. `has_industry` is a boolean; filtering it against a string value is either a
malformed query or, depending on Cube's coercion, a silently wrong count — the same
silent-wrong-answer failure mode #25's resolution ladder targets, one level up: #25 resolves
values against a known dimension once the agent has chosen the right dimension, but does not
correct the agent for choosing the wrong dimension in the first place.

## Measure/dimension precision and recall: two real misses, one artefact of the harness

- **q01** ("how many matters in total") selected `deal_points.count_distinct_matters` where the
  eval set expected `deal_points.matters_total` — both are correct counts of the same 152
  matters (`matters_total` is documented as an alias of `count_distinct_matters` kept for the
  coverage grid). Recorded as a miss because the harness grades exact measure names, not
  semantic equivalence — a limitation of the harness, not a model error.
- **q07** and **q09** genuinely missed: q07 selected only `comparable_deals.n` with an unrelated
  filter instead of `present_count`/`n` filtered by `deal_point_name`; q09 selected no dimension
  breakdown despite the question explicitly asking to "break down ... by position."

## Per-case results

Full detail (25 rows, precision/recall per case, `None` for refusal cases) is in
`docs/eval/recorded_outputs.json` alongside `docs/eval/measure_selection.json`; both are
committed so the numbers above are reproducible from the same inputs the harness reads, and
`backend/tests/test_measure_selection_eval.py` re-derives the aggregate on every CI run (no
network, asserted by making socket construction fail during the test).

## Not done

- No further prompt or vocabulary change beyond the one exclusion above. The two remaining
  concrete fixes this eval surfaces — giving the model the actual industry label values (or a
  stronger instruction to use `comparable_deals.label`, not `has_industry`, for industry
  filters) and an explicit "you may decline" instruction for out-of-schema questions — are
  natural follow-ups, deliberately not made here to avoid iterating the prompt against this
  specific 25-question set, which would overfit the eval rather than improve the agent.
- Measure equivalence (q01's `matters_total` vs. `count_distinct_matters`) is not handled — the
  harness grades exact name sets. A future revision could accept a documented alias list.
- Run-to-run non-determinism (noted above) means a single recorded run is a sample, not a fixed
  ground truth about the model's behavior; a production eval would average several recordings.

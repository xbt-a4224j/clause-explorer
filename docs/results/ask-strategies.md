# Which strategy turns a lawyer's question into a governed selection

Measured 2026-09-06, `gpt-4o-mini`, against `docs/eval/ask_questions.json` — 24 questions a
transactional lawyer would ask of a public-target merger-agreement corpus. **20 have a correct
ABA deal point; 4 must be declined**, because the corpus genuinely cannot answer them: deal
value is NULL on all 152 matters, and MAUD has no go-shop point, no fee amounts and no adviser
names. Declining those is a right answer, and a strategy that invents a nearest match for them
is worse than one that answers fewer questions.

The answer key is written against the MAUD taxonomy rather than against any implementation, so
every strategy is scored on the same list.

Harness: `backend/explorer/evals/ask_bench.py`. Reproduce with
`PYTHONPATH=backend python -m explorer.evals.ask_bench`.

## Results

| strategy | calls | total /24 | answerable /20 | declines /4 | $/run | s/run |
|---|---|---|---|---|---|---|
| free-form, free choice over 11 measures | 1 | **4** | 0–1 | 3–4 † | 0.0030 | 22 |
| shape, then deal point | 2 | 15–16 | 12–13 | 3 | 0.0050 | 23–25 |
| deal point, then shape | 2 | 19 | 16 | 3 | 0.0056 | 24 |
| one call, both choices enum-constrained | 1 | 20–21 | 17–18 | 3 | 0.0054 | 13 |
| + each deal point listed with its answers | 1 | 22 | **20** | 2 | 0.0157 | 15 |
| + strict-null prompt instead | 1 | 19 | 15 | **4** | 0.0057 | 13 |
| **+ answers AND a `covers_the_question` check** | 1 | **23** | 19 | **4** | 0.0160 | 17 |

† The free-form row's declines are **degenerate**: it declines everything, because it never
locates a deal point at all. It is not being cautious; it cannot see the taxonomy.

## What actually moved the number

**Deciding shape and deal point together beat deciding them in sequence** — and at half the
calls and half the wall-clock. They are not independent: knowing a question is about a tail
period already tells you it wants a number rather than a distribution. Splitting the decision
threw that away and made each half guess without the other.

**Listing each deal point with the answers it takes was the single biggest lever**, 18/20 to
20/20 on answerable questions. The ABA names are cryptic — `W/N/A/F applies to-Answer`,
`A/P/C application to-Answer` — while their *answers* say plainly what the question is:

```
Knowledge Definition-Answer            :: Constructive knowledge | Actual knowledge
Ordinary course efforts standard-Answer:: Flat covenant | Commercially reasonable | Reasonable best
```

It costs tokens rather than work — the grouping already feeds the facet rail — and roughly
triples the prompt, from ~1,400 to ~4,300 tokens. That is **$0.0007 a question instead of
$0.0002**, which is not a consideration.

**A structural self-check beat a sterner prompt.** Telling the model to be strict about null
fixed all four impossible questions and cost five real answers (20/20 → 15/20). Asking it to
choose *and then separately state whether the choice covers the question* kept 19–20 answers
**and** got all four declines. The model is markedly better at auditing a concrete pairing than
at calibrating caution in the abstract.

Naming the missing terms in the prompt — "this taxonomy has no go-shop" — would have scored
higher and would be **overfitting to this question set**. It would not survive a term nobody
thought of, and it is the kind of thing that looks like a result and is not one.


## Correction — the headline was measured with a broken metric

**The 23/24 first published here was wrong**, and the way it was wrong is worth more than the
number was.

Grading checked only the **deal point** and ignored the **shape**. So a strategy that found the
right term and then chose `coverage` instead of `distribution` scored as correct — while the
deployed app returned `n=152`, the size of the corpus, instead of the split. A metric that reads
half the output certifies half the system.

Under shape-aware grading, on 27 questions (20 answerable, 7 that must decline), the same
shipped prompt scores **7 of 27, with 5 of 20 answerable**. That is the honest baseline.

Two prompt changes, each measured on its own:

| | total /27 | answerable /20 |
|---|---|---|
| as first shipped | 7 | 5 |
| drop the `coverage` shape | 8 | 6 |
| **name `distribution` the DEFAULT and list its phrasings** | **17** | **15** |
| **+ decline when the COMPUTATION is inexpressible** | **20** | **16** |

`distribution` described merely as "the usual case" lost two thirds of the answerable questions
to `count` and `coverage`. Naming it the default and enumerating the phrasings — "how many deals
have X", "do agreements include X", "is X usually A or B" — more than doubled the score.

The second clause covers a different kind of unanswerable: not absent DATA but absent
COMPUTATION. "Which of these agreements is most off-market" needs a window function over a
matters-grained score; a Cube selection describes one slice on one deal point. Before the clause
that question returned **152**.

Both are in the shipped prompt, and `evals/ask_bench.py` now imports it rather than holding its
own copy — the two had already drifted once.

**Still failing at 20/27**: one deal-point confusion (ordinary course efforts standard →
Buyer consent requirement), two median/distribution mixups, and three of the seven declines.

## Temperature 0 is not determinism

Three identical runs of the winning strategy, same prompt, same model, `temperature=0`:

```
23 / 24        21 / 24        22 / 24
```

The first run was the one worth publishing and it would have been wrong to publish it. A single
run is a sample, not a measurement, and reporting the best of three as "the score" is the same
error this repo's calibration harness already learned expensively — two identical extraction
runs there differed by **36 correct out of 1,704**.

Temperature 0 is set anyway: narrowing the spread is worth having even when it does not close
it, and a figure a partner cannot reproduce is worth less than one they can.

**The honest headline is 20 of 27 under shape-aware grading** — see the correction above. The
22 ± 1 figure came from the metric that ignored shape.

## What is not measured here

- **The full matrix at three trials.** The account hit its **requests-per-day cap (10,000)**
  partway through. The single-run column stands; the variance figure is from three runs of the
  winner only. Worth noting what ran out: a *request count*, not spend — the whole night's
  experimenting cost single-digit dollars. A cost ceiling would not have prevented it.
- **A held-out question set.** These 24 questions were written by the same person who tuned the
  prompts against them. That is a smoke test with an answer key, not a benchmark. A real number
  needs questions written by someone else, and the floors tuned on a train split.
- **Whether the chosen deal point is the *best* one.** Grading is substring containment, and
  four questions are genuinely served by more than one ABA point ("fiduciary out" maps to two).
  Any of them counts as correct, which is right for a lawyer's purposes and generous for a
  benchmark's.

## Baseline, for scale

Before any of this, the same ten-question subset run end to end through `/agent/ask` then
`/agent/run-selection` produced **0 of 10** answers to the question asked — not near misses, but
empty selections, 503s, and `how many deals are all cash` refused at n=0 when the answer is 89.

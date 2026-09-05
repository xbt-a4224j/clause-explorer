# Demo scripts

Two scripts, about **four minutes each**. Every number below was observed on the running stack
on 2026-07-31 and re-verified end to end before this file was written. If something on screen
disagrees with a number here, trust the screen and stop rather than talk over it.

**Before you start**

```bash
docker compose up -d --build      # neither api nor web bind-mounts source; restart alone serves stale code
```

Open http://localhost:5173 and **hard-refresh**. Check the status strip is green, then click
through both scripts once, cold — Cube's first query after a restart is slow and you want that
latency spent before anyone is watching.

---

## Script 1 — "What have we got that looks like this?"

**Audience:** anyone. This is the product working.
**Claim:** the comparison an associate builds by hand from eight agreements, with every figure
carrying its denominator and drilling back to the contract text.

### Beat 1 — what is loaded (20 s)

Land on **Explore**. Read the line under the title:

> `152 matters · 12,937 deal points · 14 industries`

Then point at the provenance line beneath it and say the honest part **first**:

> "Matters and deal points are MAUD — the Merger Agreement Understanding Dataset, 152 public
> merger agreements that lawyers annotated. Industries come from a SIC crosswalk over SEC
> EDGAR codes and are
> **inferred**, not labelled. And the corpus is twenty months, March 2020 to November 2021 — so
> nothing I show you is a claim about the last five years."

*Leading with the limits buys you everything that follows.*

### Beat 2 — narrow it (45 s)

Facet rail → **Industry → Health Care Industry**. The other groups recompute.

Three things to say while it lands:

- **`134 filterable`** on the Industry header — *"that is not 152. Eighteen matters have no
  industry at all, and the header counts what the dimension can actually narrow."*
- The **`inferred`** badge — *"this is the one axis that is classifier output. It says so where
  you filter on it, not in a footnote."*
- **`unclassified · n=18`** carries its own reason — *"EDGAR did not resolve the registrant to
  an SIC code. That is a provenance fact, not a bug."*

If someone asks about **Deal size**: it is disabled and says why. *"EDGAR's company endpoints
carry no transaction value, so rather than estimate one I left it empty and turned the filter
off."*

Then point at **Consideration** — All Cash 89 · All Stock 39 · Mixed 24 — and note it is
**not** inferred: *"that one is read straight from a lawyer's annotation."*

### Beat 3 — the ranked set (30 s)

Search: **`healthcare take-private by a sponsor`**. You get **8 of 25 candidates**, ranked:

```
contract_62   GENMARK DIAGNOSTICS, INC.        2021-03-12   0.956
contract_142  VIELA BIO, INC.                  2021-01-31   0.893
contract_82   LUMINEX CORPORATION              2021-04-11   0.753
contract_55   FIVE PRIME THERAPEUTICS, INC.    2021-03-04   0.749
contract_32   CONSTELLATION PHARMACEUTICALS    2021-06-02   0.642
contract_43   DICERNA PHARMACEUTICALS, INC.    2021-11-17   0.623
contract_88   MAGELLAN HEALTH, INC.            2021-01-04   0.623
contract_12   BIOTELEMETRY, INC.               2020-12-18   0.600
```

> "Keyword matching blended with semantic similarity — hybrid, weight 0.5, and the weight is
> configuration, not a constant. The part I would defend is that both score distributions are
> min-max normalised per query before they are blended. BM25 is unbounded, cosine sits in
> roughly [0, 1]; add them raw and BM25 swamps the vector term, `alpha` silently stops meaning
> what it says, and the results are still plausibly ordered — just not by the weighting anyone
> chose. `backend/tests/test_hybrid_retrieval.py` asserts it."

*Which of the three methods wins is **not measured**. #53 removed the ablation that tried:
two of its three query phrasings named the parties verbatim and saturated at 1.000 recall@1,
so the aggregate was dominated by a task nothing could fail. Say that rather than quoting a
number the eval did not support.*

### Beat 4 — the rollup (60 s)

Switch to **Deal Terms**. Selection carries over. **92 rows** over **n=8**.

| Row | What to say |
|---|---|
| `Pandemic … Specific reference to COVID-19` — **7 of 8** | "Seven of these eight name COVID explicitly. Across all 152 it is 144." |
| `Fiduciary exception: Board determination standard` — **3 of 8** | "This is where the set actually differs. That is the row a partner cares about." |
| Any row reading **`7 of 7`** | "Look at the denominator — seven, not eight. One agreement does not answer that question at all, so it is excluded from its own denominator rather than counted as a no." |

Then the rule, once:

> "Nothing here renders as a percentage — zero of ninety-two rows do, because n is 8 and a
> percentage over eight deals implies precision the sample cannot support. Above thirty it
> switches. And **eight rows read `0 of 8`** — a deal point none of them has still appears,
> because absence is a finding and a missing row would read as 'nobody asked'."

### Beat 5 — the payoff (45 s)

Click into the COVID row → drill-through:

```
BIOTELEMETRY, INC.   contract_12.txt  [33470, 37923]
"Material Adverse Effect" means any event, change, development, circumstance, fact or
effect that, individually or taken together with any other events … -10- …
```

> "That is the exact byte range from the downloaded filing — not a summary, not a paraphrase.
> Including the page-break artefact, because cleaning it up would make the text untraceable. A
> row whose text cannot be traced to a byte range is a bug here, and there is a test that
> re-reads the file at those offsets to prove it."

If asked how reliable: **12,442 of 12,937 spans located, 96.2%.** The other 495 store NULL
rather than a guess, because a wrong offset opens the wrong clause and looks completely right.

### End on

> "The ABA publishes this comparison for the whole market, by hand, every two years. This is the
> same thing scoped to the eight deals in front of you, and every figure drills back to the paper."

---

## Script 2 — "How do you know it's right, and what happens when it isn't?"

**Audience:** the technical skeptic. Lead with this one for a data-science reviewer.
**Claim:** correctness here is discrete and gradeable, and the system declines when it cannot
answer.

### Beat 1 — the vocabulary (40 s)

Open **Semantic Layer**. Point at `Label space: 56` — 16 measures, 40 dimensions.

> "An agent answering analytical questions has two independent ways to be wrong: the number, and
> the *definition* of the number. If it writes SQL it picks both, and you are left diffing two
> plausible queries with no way to score either. Here it selects from these fifty-six names and
> nothing else. Correctness becomes one discrete question — did it pick the right measure and
> filters — which is gradeable offline, with no database and no model."

Unprompted:

> "Read live from Cube's metadata endpoint, not a checked-in copy. A stale copy could disagree
> with the models, and then every selection failure becomes an argument about which list was
> authoritative."

### Beat 2 — build one (60 s)

Scroll to **Build a query by clicking**. Say the structural point before clicking anything:

> "There is no text box in this panel. That absence is the feature — you select from the
> vocabulary or you select nothing. Try to construct a measure that does not exist; there is no
> way to express one."

Click **"How many of these agreements mention COVID-19 by name?"** → **Run** → `144 of 152`.

> "The number was computed by Postgres. The model's only job in this architecture is picking
> which named measure answers the question."

Spare thirty seconds? Click **"How long does a target get to match a competing offer?"** →
**median 4 business days, n=147**:

> "That is `percentile_cont`, never `avg`. There is exactly one average in the model and it is
> called `mean_numeric_value_do_not_use_for_market` — and it is excluded from the vocabulary
> outright, so a direct API call gets a 422."

### Beat 3 — make it refuse (45 s)

Click **"What if I narrow it down to a single company?"** → **Run**:

> `Refused — n=1, threshold 5`

Let it sit a second, then:

> "Three jobs, one threshold. It is statistically honest — a median over three deals is not
> market. It gates on extraction confidence. And it is **k-anonymity**: if I can filter until one
> deal remains, I have extracted a single client's negotiated term through the analytics layer
> without ever opening a document. At a firm that is a confidentiality control, not a nicety."

Close the loophole before they ask:

> "The gate is server-side. A raw `curl` gets the same refusal — and it returns an empty row list
> **and** a refused flag, because 'we will not answer this' and 'there is nothing here' are
> different statements."

Have this pasted in a terminal, ready:

```bash
curl -s -X POST localhost:8000/agent/run-selection -H 'content-type: application/json' \
 -d '{"measures":["deal_points.n"],"dimensions":[],"filters":[
   {"member":"deal_points.deal_point_name","operator":"equals","values":["FLS (MAE) Standard-Answer"]},
   {"member":"comparable_deals.target_name","operator":"equals","values":["TCF FINANCIAL CORPORATION"]}]}'
# {"rows": [], "n": 1, "refused": true, "threshold": 5, ...}
```

### Beat 4 — the grade, which is mostly bad news (60 s)

Scroll to **The grade**:

```
11 of 20   answerable questions, exact selection match
 1 of 5    questions it should have declined — and mostly did not
```

Do not soften it. Lead with the second number:

> "The model answered four of five questions it should have refused. That is the worst number in
> the project, and it is also the argument for the architecture: refusal cannot be the model's
> job when this is how well it does it. Which is exactly why `min_n` is enforced in the API and
> not asked for in a prompt."

Then the caveat about your own grader:

> "And the eleven understates it. Look at q01 — marked wrong for selecting
> `count_distinct_matters` where the case expected `matters_total`, and my own Cube model
> documents those as the same measure under two names. My grader cannot see an alias. That is a
> finding about the vocabulary, not the model."

Finish with what makes the table possible:

> "Computed from two committed fixtures with no database and no model call — there is a test
> that forbids a database connection during it. Freeform text-to-SQL has no equivalent. That is
> the whole argument: not that its SQL is wrong, it is usually right, but that there is no table
> like this one you could build for it."

### Beat 5 — if there is time (30 s)

**Coverage**: `33 of 45` cells refuse, `12` are reportable.

> "A gap is more actionable than a strength you already knew about, so the thin cells are the
> loud ones. Two thirds of this grid declines to answer."

### End on

> "The annotations are not the product — they are the error bar. Because lawyers labelled these
> 152, I can run an extractor against a held-out slice and publish accuracy per deal point. Four
> of the five I have measured fall below the reporting threshold. That is what makes 'this works
> on documents nobody annotated' a testable claim instead of a sales line."

---

## Answers to have ready

| If they ask | Say |
|---|---|
| "Why Cube, for 152 rows?" | "For the published vocabulary, not the speed. `/meta` is what lets an offline eval and a running agent grade against the identical list. A 200-line Python registry gets most of it — what it does not get is the catalog being a contract." |
| "Could this connect to Tableau?" | "Yes — Cube exposes a Postgres-wire SQL API, so a BI tool consumes the governed measures directly. Config change, not a rebuild. I did not build it: proprietary, and a live surface with no demo payoff." |
| "How big can this get?" | "Not far, honestly. 152 documents, embeddings in a 9.5 MB committed file, no pre-aggregations. All three are deliberate at this size and all three break somewhere in the low thousands." |
| "Is the industry data any good?" | "No — and it says so. Self-assigned SIC through a hand-written crosswalk, 134 of 152 resolved, and a hand check of twenty found three carrying the *acquirer's* industry rather than the target's." |
| "Why is Health Care 25?" | "My crosswalk groups pharma, biotech, devices and CROs with providers. Straight NAICS gives 3. That grouping is mine, not a standard, and the UI says so wherever it appears — it is the judgement call most open to challenge." |
| "What would you do next?" | "Deal value, properly — the one axis the product promises and does not have. And calibration beyond five of ninety-two deal points, because right now I can only make an accuracy claim about five." |

## Do not say

- **"the last five years"** — it is twenty months, 2020-03-13 to 2021-11-21
- **"our matters" / "the firm's deals"** — public SEC filings, not any firm's history
- **"75%"** for anything at n=8 — the product refuses to; do not do it verbally either
- **"accurate"** unqualified — give the per-deal-point number, or say it is not measured

## Rehearsal checklist

- [ ] `docker compose up -d --build` from cold, then hard-refresh
- [ ] Both scripts run end to end without touching a terminal mid-demo
- [ ] Script 1 beat 5 opens real clause text with a byte range
- [ ] Script 2 beat 3 shows the refusal, `curl` pasted and ready
- [ ] No console errors on any tab
- [ ] Both work with `OPENAI_API_KEY` unset — nothing in either needs a model

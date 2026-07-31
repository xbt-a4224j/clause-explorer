# Walkthrough

Three worked examples, each run against the live stack — no invented numbers. Every figure below
traces to a command shown beside it; full terminal transcripts are committed under
`docs/results/walkthrough-script{1,2,3}.txt`.

```
$ docker compose ps
api running · cube running · db running · web running
```

---

## 1 — Find comparable deals

**Tab: Explore.** Corpus counts are visible on landing, before any filter is applied:

```
$ curl -s -X POST localhost:8000/facets -d '{}'
corpus: 152 matters · 12937 deal points · 14 industries
```

The industry facet, unfiltered — every count is a live Cube query, not precomputed:

```
Finance and Insurance Services Industry    n=25
Health Care Industry                       n=25
Manufacturing Industry                     n=22
unclassified                                n=18
Information Industry                        n=18
```

Narrow to Health Care. Every **other** facet updates against the narrowed set; the industry
facet itself keeps all 15 values so the selection stays switchable:

```
$ curl -s -X POST localhost:8000/facets -d '{"folio_industry_label":"Health Care Industry"}'
total_n=25 of unfiltered_n=152
year 2021          n=19
year 2020           n=5
year unclassified    n=1
```

Rank within the filtered set (`limit=8`, the same 8 matters script 2 rolls up):

```
$ curl -s -X POST localhost:8000/comparables \
    -d '{"folio_industry_code":"RCSG4k3ah1Pu5YgPexPgOmL","limit":8}'
candidate_count=25 returned_count=8
rolled_up_to_descendants=91

contract_1     ACCELERON PHARMA INC.        2021-09-29  inferred=True
contract_104   PPD, INC.                    2021-04-15  inferred=True
contract_105   PRA HEALTH SCIENCES, INC.    2021-02-24  inferred=True
contract_107   MERCK SHARP & DOHME CORP.    2021-02-24  inferred=True
contract_113   PREVAIL THERAPEUTICS INC.    2020-12-14  inferred=True
contract_12    BIOTELEMETRY, INC.           2020-12-18  inferred=True
contract_127   SOLITON, INC.                2021-05-08  inferred=True
contract_136   TRANSLATE BIO, INC.          2021-08-02  inferred=True
```

**What must be true, verified:** `candidate_count=25` matches the facet count exactly — the same
25 either way, because `/comparables` filters in Postgres first and ranks only the survivors
(#18), never the other way round. Every matter here carries `inferred=True` on its industry
label, because the FOLIO code comes from a SIC crosswalk, not a MAUD expert annotation — and the
card renders that badge, never silently.

**Note on scope, stated plainly rather than glossed over:** the corpus spans 20 months
(2020-03 → 2021-11), not "the last five years," and there is no sponsor-side flag in MAUD or
EDGAR — "sponsor-side" is the reader's own context for this healthcare slice, not a filter the
product offers. `deal_value_usd` is NULL on all 152 matters (#9 open), so this walkthrough
narrows by industry and year, which are populated, not by deal size.

---

## 2 — What was negotiated across these 8

**Tab: Deal Terms.** The same 8 matter ids from script 1, rolled up:

```
$ curl -s -X POST localhost:8000/deal-terms -d '{"matter_ids":[...8 above...]}'
selection_n=8  threshold=30  answered=90  absent=2
rows rendered as a percentage: 0   (n=8, below threshold=30 — counts only, by rule)
```

`Knowledge Definition-Answer` — every one of the 8 answers it, but not the same way:

```
Knowledge Definition-Answer: 8 of 8
    Constructive knowledge = 5
    Actual knowledge = 3
```

Drill through to the actual clause language behind that split — not a list of matter ids, the
text itself, with the source file and the exact character range it came from:

```
$ curl -s -X POST localhost:8000/deal-terms/drill \
    -d '{"matter_ids":[...],"deal_point_name":"Knowledge Definition-Answer"}'

contract_1 (ACCELERON PHARMA INC.) -> Constructive knowledge
  maud/data/contracts/contract_1.txt [255704, 256033)
  "Knowledge" of Parent or the Company... means the actual knowledge of the individuals
  set forth on Schedule 9.3 after making reasonable inquiry...

contract_104 (PPD, INC.) -> Actual knowledge
  maud/data/contracts/contract_104.txt [279332, 279676)
  "knowledge" of any Person that is not an individual means... the actual knowledge of
  such Person's executive officers...
```

**What must be true, verified:** contract_1's clause explicitly requires "reasonable inquiry" —
that's what makes it *Constructive* rather than merely *Actual* knowledge, and reading the two
excerpts side by side is what makes the distinction legible instead of taken on trust. Every
quoted string above is byte-identical to the downloaded contract at the stated offsets — asserted
by a pinning test (`backend/tests/test_deal_terms.py::TestDrillThroughIsTraceable`), not just
eyeballed here. The scope note ships
on the response itself: *"These are comparable PUBLIC deals from the MAUD study... not this
firm's own matter history"* — stated on the data, not left to UI copy that could drift from it.

---

## 3 — It declines when it can't answer

**Tab: Coverage**, first — where the corpus is thin, before anyone clicks anything:

```
$ curl -s -X POST localhost:8000/coverage -d '{}'
grid 15x3 = 45 cells · min_n=5
thin: 33 of 45   reportable: 12 of 45
```

33 of 45 industry × year cells are below `min_n`. That is the product's central finding about
its own data, not a bug: most slices of a 152-matter corpus are too thin to characterize once
you cut by two dimensions at once.

**Tab: Deal Terms**, narrowed to 3 matters — below the threshold:

```
$ curl -s -X POST localhost:8000/deal-terms -d '{"matter_ids":["contract_1","contract_104","contract_105"]}'
{
  "selection_n": 3,
  "rows": [],
  "refused": true,
  "refusal": {
    "reason": "insufficient_n",
    "n": 3,
    "threshold": 5,
    "message": "n=3 — insufficient to characterize (threshold 5)"
  }
}
```

Not an empty result — a distinct response shape (`refused: true` plus a `refusal` object naming
the actual `n` and the threshold), rendered as its own visual state in the UI, `role="status"`,
never mistaken for "no terms found."

**The gate is server-side and cannot be bypassed from the client:**

```
$ curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8000/deal-terms -d '{"matter_ids":[]}'
422

$ curl -s -X POST localhost:8000/deal-terms \
    -d '{"matter_ids":["contract_1"],"admin":true,"bypass_min_n":true}'
refused: True | n=1 — insufficient to characterize (threshold 5)
```

Extra fields in the request body do nothing, because nothing reads them — there is no flag that
turns the gate off. Drill-through carries the same check independently: a rollup refusal that
didn't also block drill-through would be decorative, since drill-through returns a named
matter's actual clause text — the sharper of the two risks.

**The rationale, three jobs at once:** statistical honesty (`n=3` cannot support a claim about
what's "typical"), extraction-confidence gating (the same threshold structurally excludes any
deal point whose calibrated accuracy — #28 — falls below it), and k-anonymity. An analyst who
narrows a filter to `n=1` and asks "what does this deal say" has extracted one client's
negotiated term through the aggregate layer, around the ethical wall, without ever retrieving a
document — and even the *count* form of the answer (`"1 of 1"`) is exactly as identifying as the
document itself would be. At a firm, that is a confidentiality control, not a nicety.

---

## Rehearsal checklist, verified this session

- [x] Cold start: `docker compose ps` shows all four services healthy
- [x] All three scripts run end to end against the running stack, not mocked
- [x] Every number on screen carries its `n` (`n=25`, `n=8`, `n=3`, `min_n=5`)
- [x] Scripts 1 and 2 run with `OPENAI_API_KEY` unset — retrieval and aggregates are keyless
- [x] This file records real observed output for all three scripts

Full transcripts: [`docs/results/walkthrough-script1.txt`](results/walkthrough-script1.txt),
[`script2`](results/walkthrough-script2.txt), [`script3`](results/walkthrough-script3.txt).

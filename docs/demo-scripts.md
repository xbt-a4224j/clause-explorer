# Demo scripts

Three scripted walkthroughs. **These are the acceptance test for the product as a whole** —
every implementation decision should be checked against "does this make one of these land?"

A feature that serves none of them is out of scope. A rough edge on the path of one of them
is a bug, not polish.

Numbers below are placeholders marked `‹measured›` until a real run fills them in. Nothing
here is quotable until it has been observed.

---

## Script 1 — "Find me comparable deals" (Explore)

**Who:** a partner preparing a pitch for a healthcare private-equity sponsor.

> **Corpus limits this script must respect** (measured, see `docs/worklog.md` #11): the corpus
> spans **20 months**, 2020-03-13 → 2021-11-21 — never say "last five years". There is no
> sponsor-side flag in MAUD or EDGAR, so "private-equity sponsor" is the partner's context, not
> a filter the product offers. Health Care is n=25 because our crosswalk groups pharma, biotech,
> devices and CROs with providers; NAICS does not, and the UI must say the grouping is ours.
**The ask:** *what have we got that looks like this deal?*

### Beats

1. Land on **Explore**. Corpus counts are visible before any interaction —
   `‹measured› matters · ‹measured› deal points · ‹measured› industries`.
2. Type into search, or press `/`. Filter down with the facet rail:
   industry → Health Care (n=25 of 152, measured 2026-07-30), year → 2021.

   > **Size band is not in this script.** `deal_value_usd` is NULL for all 152 matters — EDGAR's
   > company endpoints carry no transaction value (#9 is open on it). A size facet would render
   > as an empty rail, so the script filters on industry and year, which are populated. Restore
   > the size beat when #9 closes, not before.
3. **Facet counts update live as each filter lands.** Zero-count values grey out rather than
   disappearing — you can see what the corpus does *not* have.
4. Results rank by similarity. Each matter card shows parties, industry, size, date, and the
   headline terms negotiated.
5. Expand a card → the deal points for that matter, with clause text.
6. **Copy summary** → a pitch-ready paragraph with a citation back to the source agreement.

### What must be true

- Facet counts are live Cube queries, not precomputed
- The industry badge shows **inferred** where the FOLIO code came from a classifier
- `/` focuses search, `j`/`k` move the result list, `Enter` opens — no mouse required
- Empty and loading states are designed, never a spinner on a blank panel
- Every count carries `n`

### The line to say

> Filtering is against a legal ontology, not string matching — so "healthcare" rolls up
> medical devices, pharma and providers, and I can drill into any one of them.

---

## Script 2 — "What did we negotiate across these?" (Deal Terms)

**Who:** same partner, now with eight comparables on screen.
**The ask:** *instead of reading eight merger agreements, tell me what's in them.*

### Beats

1. From the Explore result set, switch to **Deal Terms**. The selection carries over.
2. One row per deal point, prevalence across the selected set:
   `fiduciary exception — ‹measured› of 8`, `ticking fee — ‹measured› of 8`,
   `reverse termination fee — median ‹measured›% (n=8)`.
3. **Counts, not percentages**, because n=8 cannot support a percentage.
4. A deal point absent from every deal shows as `0 of 8` — absence is a finding, not a
   row to omit.
5. Click any row → the actual clause language from the deals that have it, with source file
   and character offsets.

### What must be true

- The rollup is a Cube query filtered to the selected matter IDs — paste the real
  request/response into the work log
- Rendering switches from counts to percentages at a configured threshold, tested at the boundary
- Medians are `percentile_cont`, never `avg` — reverse-termination-fee mean and median diverge
- Drill-through resolves to real source spans, verified against the downloaded corpus

### The line to say

> This is the comparison chart an associate builds by hand from eight agreements. The ABA
> publishes it annually for the whole market; this is the same thing scoped to the set in
> front of you.

---

## Script 3 — "It declines when it can't answer" (Coverage → refusal)

**Who:** a KM director, then anyone who tries to over-narrow.
**The ask:** *where are we thin — and what happens when I ask anyway?*

### Beats

1. **Coverage** tab: FOLIO industry × deal-size grid.
2. **Thin and zero cells are visually loud**, not faded. A gap is more actionable than a
   strength you already know about.
3. Cells below `min_n` are marked *insufficient to characterize* — you know before clicking
   that the rollup will decline.
4. Click one anyway → Explore, pre-filtered → Deal Terms → **the refusal state**:
   `n=3 — insufficient to characterize (threshold 5)`. Its own visual state, distinct from
   "no results".
5. Try to bypass it with a direct API call. It refuses there too — the gate is server-side.

### What must be true

- `min_n` enforced in FastAPI, not the frontend; a raw `curl` cannot get a number out of a
  thin slice (show this live)
- Refusal message states the actual n and the threshold
- Refusal is visually distinct from an empty result set
- Coverage grid and Deal Terms agree about which cells are reportable

### The line to say

> Three jobs, one threshold. It's statistically honest, it gates on extraction confidence —
> and it's k-anonymity: if you can filter until n=1, you've extracted one client's negotiated
> term through the analytics layer without ever opening a document. At a firm that's a
> confidentiality control, not a nicety.

---

## Rehearsal checklist

- [ ] Cold start works: `docker compose down -v && docker compose up --build && make ingest`
- [ ] All three scripts run end to end without touching a terminal mid-demo
- [ ] Every number on screen carries its `n`
- [ ] No console errors in any tab
- [ ] Scripts 1 and 2 work with `OPENAI_API_KEY` unset (retrieval and aggregates are keyless);
      only the agent view needs a key
- [ ] `docs/walkthrough.md` (#32) records real observed output for all three

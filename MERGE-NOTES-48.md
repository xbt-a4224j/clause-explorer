# Merge notes — #48 (collapse to one product)

This branch cuts the Coverage and Tables tabs, renames Semantic Layer to **Ask** and moves it
second, drops `GET /{table}/export.csv`, and reduces the Overview journeys from three to two.

`README.md` was **not edited** on this branch, by instruction. Every passage below is now wrong
and needs the stated fix before this merges. Line numbers are against `README.md` as of this
branch's base.

## README passages this change makes wrong

| Line | Current text | What it should say |
|---|---|---|
| 3–4 | "Find deals like the one in front of you, see what was negotiated across them, and know where your experience is thin." | The third clause was the Coverage tab. The product is now one sentence: ask in words, get a governed number you can defend — or a refusal. |
| 6 | Image alt "Overview — three journeys, each with the path it takes through the app" | Two journeys. |
| 8–10 | "Three questions, the person who asks each one … The tab bar splits after Coverage: four tabs are the product, four are the evidence" | Two questions. Six tabs, not eight: the bar splits after Deal Terms — four are the product (Overview, Ask, Explore, Deal Terms), two are the evidence (Admin, Label). |
| 12 | Heading "## Three journeys" | "## Two journeys". |
| 14–16 | Journey 1's narration begins at Explore | It begins at Ask: the question is put in the governed vocabulary, then Explore narrows, then Deal Terms rolls up. |
| 40–43 | "**2 · Is that actually market?** *An associate…*" | Journey 2 is cut. Its base-rate figures (flat covenant 9, commercially reasonable 8, reasonable best 3, n=20) are still true and can move into journey 1's Deal Terms beat rather than being deleted. |
| 57 | "**3 · Where can the extractor be trusted?**" | Renumbers to **2 ·**. |
| 45, 47–50 | Screenshot alt and caption "Semantic Layer — the query builder refusing a slice of one" / "*Semantic Layer. The agent selects from named measures…*" | The tab is **Ask**. The screenshot file name (`docs/img/refusal.png`) is unchanged; only the tab name in alt text and caption changes. |
| 52–55 | `![Coverage — thin cells styled prominently](docs/img/coverage.png)` and its caption | Delete both. The "a gap is a finding" argument now lives on Explore, where zero-count facet values stay visible and disabled — the Explore screenshot already carries that callout. |
| 88 | Table row "**Coverage** \| Where experience is thick or thin…" | Delete the row. |
| 89 | "**Overview** \| The three journeys above, each runnable from the card." | Two journeys. |
| 86–89 | The four-tab "product" table | It is still four rows, but they are Overview, **Ask**, Explore, Deal Terms — Ask moves up from the evidence half, Coverage leaves. |
| 91 | "And the four behind the divider, which are the evidence rather than the product" | Two behind the divider: Admin and Label. |
| 95 | Table row "**Semantic Layer** \| The vocabulary the agent may select from…" | Rename to **Ask** and move it into the product table above. The description is otherwise still accurate. |
| 96 | Table row "**Tables / Admin** \| Browsable raw data, ingest status, …" | Becomes **Admin** only, and loses "browsable raw data". `/tables/*` still exists as an API, but there is no browsing UI. |
| 180–181 | "Retrieval, facets, coverage, and every table view work **without an API key**" | "Retrieval, facets, the rollup and the catalog work without an API key." Same edit already made in `backend/explorer/api/settings.py`, `backend/explorer/retrieval/embeddings.py` and `backend/tests/test_embedding_cache.py`. |
| 186–188 | "The three journeys above, narrated end to end" | Two journeys. |

Also: `docs/img/coverage.png` is now referenced only by the README. Delete the file in the same
commit that deletes the README's Coverage screenshot block. `frontend/scripts/shots.mjs` has
already dropped the `coverage` shot and renamed the two `Semantic Layer` shots to `Ask`, so
re-running `node scripts/shots.mjs` will not regenerate it.

## Other files deliberately left stale on this branch

Not README, but the same class of problem — named here so nothing is discovered later:

- **`CLAUDE.md`** — "Three questions the product answers" (#3 is coverage); the Cube footprint
  paragraph naming the coverage grid; the tab table's Coverage and Tables rows; the
  `frontend/src/views/` layout line listing `Coverage · Tables`. Left alone to avoid colliding
  with the other agents editing this repo in parallel this round.
- **`docs/walkthrough.md`** — a whole "Coverage — why refusing is a feature" section plus a
  `curl -X POST localhost:8000/coverage` transcript that will now 404.
- **`docs/demo-scripts.md`** — script 2's "**Coverage**: `33 of 45` cells refuse" beat, and
  script 2 itself is the journey this issue cut.
- **`frontend/src/views/Label.tsx`** (line 25) and **`frontend/src/views/Admin.test.tsx`**
  (line 219) each mention Coverage or `Tables.test.tsx` in a comment. Another agent owns those
  files this round, so they were not touched.
- **`_meta/clause-explorer-walkthrough.html`** — out of repo; the issue already defers it.

## Decisions, and the cost accepted

`docs/worklog.md` is gitignored and does not exist in this worktree, so the decisions table for
this issue is here, where a reviewer of the branch will actually see it.

| Decision | Cost accepted |
|---|---|
| Journey 1 now starts on **Ask** (`tab: 'ask'`), carrying its Explore seed forward instead of applying it on arrival | "Run this" lands on a tab that cannot yet consume the seed — the filters apply one step later, when the reader reaches Explore. Until the free-text-to-selection feature lands, the first step is a query builder, not a sentence. The alternative — leaving the CTA on Explore while the card says the journey begins at Ask — makes the card lie about its own first click. |
| Kept `deal_points.matters_total` rather than deleting it with its Coverage rationale | A measure with no live caller stays in the vocabulary. Deleting it would change the eval's label space and silently alter what `docs/eval/measure_selection.json` grades against, which is a worse trade. |
| Deleted the CSV export route and its test rather than keeping the route "just in case" | Anyone who wants a CSV now has none. The route had one caller, which is gone, and an untested endpoint that builds SQL identifiers from a whitelist is exactly the thing that rots quietly. `test_health.py` asserts it stays gone. |
| Left `CLAUDE.md`, `docs/walkthrough.md` and `docs/demo-scripts.md` stale | Three docs now describe tabs that do not exist. Editing them this round risked colliding with the other agents working in this repo; they are itemised above so the next pass is mechanical rather than archaeological. |
| Moved the explainer to the bottom of Ask rather than trimming it | The tab now ends with ~200 words of argument below the freeform-SQL comparison, which is a long scroll. The issue is explicit that the argument is demoted, not weakened, and the panel is collapsed by default. |

## Deviations from the issue text, with the reason

- **No `coverage_deals` Cube members were removed, because none exist.** The Coverage endpoint
  read `comparable_deals.n / .label / .code / .signing_year / .deal_size_band` — every one of
  which the Explore facet rail also reads (`backend/explorer/api/facets.py`). Removing any of
  them would break faceting. `deal_points.matters_total`, whose description called it "kept for
  the coverage grid", also stays: the measure-selection eval's expected output names it
  (`docs/eval/measure_selection.json`), and the model's measure names are that eval's label
  space, so deleting it would silently change what the eval grades against. Both descriptions
  were reworded to stop citing a deleted surface. **The Cube model lost no members.**
- **The zero-count facet test asserts visible + disabled + `n=0`, not a per-value reason
  string.** `FacetValue.reason` is populated only for *absence buckets* ("unclassified") and
  `FacetGroup.unavailable` only for a dimension with nothing filterable; a plain zero-count
  value carries no server-supplied reason. Asserting one would encode behaviour the API does not
  produce. The adjacent test — "renders a group with no filterable values disabled, with its
  reason" — is the one that asserts a stated reason, and it is unchanged.
- **The explainer's `id` is still `semantic-layer`.** It is the localStorage key, and
  `ExplainerPanel` documents that it must not change between releases. The tab id, label, route
  and number-key shortcut all follow the rename; the storage key deliberately does not.
- **One word of the explainer prose changed**: "the published vocabulary **below**" →
  "**above**", because the panel moved beneath the catalog. The argument is otherwise verbatim.
- **Screenshots were not regenerated.** That needs a running app on `:5173` and a container
  rebuild; the stack is shared with other agents this round and the instruction was to leave it
  alone. `shots.mjs` is updated so the next run produces the right set.

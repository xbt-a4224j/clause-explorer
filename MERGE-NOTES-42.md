# Merge notes — #42, EDGAR picks the target's CIK, not the filer's

Written because this branch must not touch `README.md`. Everything below is a request to the
README's owner, plus the decisions this branch made and what each one cost.

## README passages that are now wrong

### 1. `## Limitations`, first bullet — the 17/3 figure

Current text:

> - **Industry is inferred, on every matter.** A checked-in SIC to FOLIO crosswalk over the SEC's
>   self-assigned code resolves 134 of 152. A 20-matter hand check found the registrant was the
>   target in 17 and the acquirer in 3. The grouping is ours: it puts pharma, biotech, devices and
>   CROs under Health Care (25 matters); straight NAICS would leave Health Care at 3.

Two numbers in it changed. Suggested replacement:

> - **Industry is inferred, on every matter.** A checked-in SIC to FOLIO crosswalk over the SEC's
>   self-assigned code resolves 139 of 152. The registrant is constrained to the deal's *target*
>   using MAUD's own `<Target>_<Acquirer>` deal name, so the buyer's industry can no longer land
>   on the seller's deal; a matter whose target does not resolve keeps NULL rather than being
>   filled from whoever filed. A 20-matter hand check found the registrant was the target in 19
>   and NULL in 1, with 0 acquirers (#42; the previous rule scored 14/3/2/1 on the same 20).
>   The grouping is ours: it puts pharma, biotech, devices and CROs under Health Care;
>   straight NAICS would leave Health Care far thinner.

**Do not paste a Health Care count from this note.** The distribution shifted with the 37 party
changes and I did not re-measure the per-industry counts by hand; take them from a fresh
`SELECT folio_industry_code, count(*) FROM matters GROUP BY 1` after ingest, not from memory.

### 2. The Explore screenshot caption, around line 20

Current text says **134 filterable** and *eighteen* matters with no industry. Those become
**139** and *thirteen*. The screenshot image itself (`docs/img/explore.png`) still shows the old
header, so the caption and the picture will disagree until it is retaken.

### 3. Anywhere the README says party names come from the agreement header

`target_name` is no longer taken from the header parser's role assignment alone; MAUD's deal name
has to agree, or the column is NULL. `acquirer_name` is **unchanged and still wrong one time in
seven** — see D-42-2. If the README describes party provenance, it should distinguish the two.

## What changed in the code

- `backend/explorer/ingest/maud_corpus.py` — new `deal_titles()`: `matter_id -> "<Target>_<Acquirer>.pdf"`,
  MAUD's own name for each deal. Its `Filename (anon)` column does **not** agree with the
  `contracts/contract_N.txt` numbering, so the join is on annotation text and is verified to
  resolve all 152.
- `backend/explorer/ingest/edgar.py` — new `deal_title_words`, `title_role`, `target_candidates`,
  `identify_registrant`; `_candidates` removed. `enrich()` now takes a `titles` argument.
- `backend/tests/test_edgar.py` — `TestTitleRole` and `TestTargetConstrainedIdentification`,
  all offline, covering filer-is-target, filer-is-acquirer, and no-match.

## Measured (all 152 matters, cached EDGAR responses, no network)

| | before | after |
|---|---|---|
| `sic_code` / `folio_industry_code` resolved | 134 | **139** |
| `target_name` | 144 | 143 |
| `acquirer_name` | 125 | 125 (deliberately unchanged — see D-42-2) |
| `signing_date` | 149 | 149 |
| identified registrant changed | — | **37 of 152** |

Of the 37 changes: 13 newly identified, 16 a different name, 8 now NULL. Of those 8, 5 were the
acquirer (correctly dropped) and 3 were a target-*side* entity that is not the target — an
operating partnership or a buyer subsidiary.

Placing the **old** rule's registrant against MAUD's deal name across all 152: target 110,
acquirer 15, unplaceable 9, none 18. The acquirer-industry error was on 15 matters, not 3.

## Decisions, with the cost accepted

| id | decision | why | cost accepted |
|---|---|---|---|
| D-42-1 | The registrant must be placeable as the **target** against MAUD's deal name, or the matter gets NULL | The buyer's SIC on the seller's deal is invisible in the UI and wrong in every rollup. A NULL is visible: it lands in the Coverage grid's thin cells | 3 matters that previously carried a plausible, target-side industry (contract_29 Columbia Property, contract_107 Pandion, contract_140 VEREIT) now carry none. Two of the three had the *right* industry from the wrong legal entity |
| D-42-2 | `acquirer_name` is left exactly as the header parser produced it — **reverted after being tried** | I first applied the same rule to it and NULLed 64 of 125. Then the retrieval tests went red: the embedded matter summary is `… / target_name / acquirer_name / industry …`, so changing 64 of them evicts 64 vectors from the committed `data/embeddings/vectors.npz`, and with no API key the app can no longer serve retrieval for those matters — breaking the CLAUDE.md hard constraint that it boots and serves retrieval with no key. #42 is about whose *industry* the matter carries, and this was not in its AC | `acquirer_name` stays wrong in a known way: MAUD's deal name says it is the **target** on 23 of 152 and cannot place it on 41 more. A matter card names the seller as the buyer roughly one time in seven. That is shipped, unfixed, and needs its own ticket — the fix is cheap in code and expensive in cache re-warming, so it should be batched with any other change that moves matter summaries |
| D-42-3 | Name matching folds case, punctuation, `INC`/`CORP`/`CO` spellings, a leading `THE`, and optionally one trailing legal suffix — but only at three words or more | MAUD's titles drop the suffix the agreements carry (`Acacia_Communications` vs `ACACIA COMMUNICATIONS, INC.`), so exact matching alone places almost nothing. The three-word floor stops `X INC` collapsing to a bare `X` | A false match attaches another company's SIC — the same failure by a different door. Hand-reviewed all 139 identifications: 0 wrong companies, 5 post-closing renames under the correct CIK, 1 name shared by two registrants (contract_129 `STERLING BANCORP`; both are SIC 6021, so the industry does not turn on it) |
| D-42-4 | A matter with no MAUD deal title is not enriched at all | There is no way to tell the sides apart without it, and the pre-#42 fallback is the bug | Currently costs nothing — all 152 have a title — but a corpus revision that breaks the text join would silently zero the industry column rather than degrading to the old behaviour. That is the intended direction and it should be loud in the ingest log if it ever happens |
| D-42-5 | `deal_titles()` joins MAUD's raw spreadsheet to contract ids on annotation text, not on `Filename (anon)` | The anon column disagrees with the extracted numbering — its `contract_35.pdf` is Michaels/Apollo, the extracted `contract_35.txt` is Performance Food Group/Core-Mark. Trusting it would have mislabelled every matter | The join reads all three label CSVs (~120 MB) and adds a few seconds to EDGAR ingest. It is cached per process. A tie in the excerpt vote yields no title, so a future corpus revision loses matters quietly unless someone watches the count |

## BLOCKER — the test suite is not green, and cannot be from this branch alone

Two committed artifacts are now stale *because the fix worked*. Neither can be regenerated
under this branch's constraints. Both must be handled before #42 is closed.

### 1. `data/embeddings/vectors.npz` needs re-warming — 40 matter summaries

The embedded summary per matter is
`source_contract_title · target_name / acquirer_name · industry_label · year`, so correcting
the industry on 37 matters and the target on 17 changes the text that was embedded.
**Measured: 40 of 152 matter summaries are no longer in the committed cache** (11,894 entries;
0 of the 14 industry labels are affected).

With no API key those 40 raise `EmbeddingUnavailable`, which fails 10 tests across
`test_comparables.py` and `test_hybrid_retrieval.py` and breaks the hard constraint that the
app serves retrieval with no key. Confirmed by controlled comparison: re-ingesting the same
database with the pre-#42 `edgar.py` makes all 24 of those tests pass again, and re-ingesting
with this branch's makes 10 fail.

The remedy is the documented one, and it needs a key:

```
python -m explorer.retrieval.warm_cache        # rewrites data/embeddings/vectors.npz
```

I did not run it: it spends the owner's OpenAI key without being asked, and `vectors.npz` is a
committed artifact other agents working in parallel may also be invalidating. **Run it once,
after all in-flight enrichment changes have landed, not per branch.**

### 2. Cube-backed assertions encode the pre-#42 industry distribution

The distribution moved, measured in the database directly (`explorer_42` vs `explorer`):

| industry | before | after |
|---|---|---|
| (unclassified) | 18 | **13** |
| Information | 18 | **25** |
| Real Estate, Rental and Leasing | 12 | **9** |
| Health Care | 25 | **26** |
| Finance and Insurance Services | 25 | **24** |
| Retail Trade | 3 | **4** |
| Transportation and Logistics | 1 | **2** |

Every other industry is unchanged. At least these assertions encode the old numbers and will
need re-measuring against a single database once Cube points at it:

- `test_comparables.py:79` — `candidate_count == 134` → 139
- `test_cube_model.py:249` — `by_flag["true"] == 134` → 139
- `test_cube_model.py:225`, `:279`, `test_filter_resolution.py:53`, `:119` — Health Care `25` → 26
- `test_facets.py:207`, `test_coverage.py:103` — recompute; they mix industry totals

**I deliberately did not edit them.** Cube is bound to the shared `explorer` database, which I
was told not to ingest into or reconfigure, so I could not observe a single one of them pass or
fail on this branch's data. Writing in numbers I could not watch go green is the fabricated-number
failure this repo exists to avoid. They are listed so the next person changes them *and sees them
pass*, in one pass, after the re-warm.

## One thing a reviewer should know about how this was verified

This branch was developed against its own database (`explorer_42`) so as not to disturb the
shared `explorer` one. **Cube is wired to `explorer` and was left alone**, so every
Cube-mediated assertion in the suite read `explorer` while the API under test read
`explorer_42`. Two consequences:

- `test_cube_model.py::TestNewRowsAppearWithoutARestart::test_an_inserted_row_is_visible_through_cube_without_a_restart`
  cannot pass under that isolation — it inserts into the database the API is pointed at and
  polls for the row through Cube, which is looking at a different database. It is not a
  regression from #42 and it passes in the normal single-database setup.
- The Cube-backed facet, coverage and deal-terms assertions that *did* pass were reading
  `explorer`'s numbers, not this branch's. **Re-run the suite against a single database
  before trusting them**, and expect the facet counts to move: this branch changes the
  industry on 37 matters, and `134 filterable` becomes `139`.

## Not done

- `docs/worklog.md` was **not** updated. It is gitignored, exists only in the main checkout
  outside this worktree, and is shared with other running agents; appending from here risked
  clobbering their writes. The decisions table above is the substitute and should be folded in.
- `deal_value_usd` remains NULL. Unchanged by this ticket, #9 still open.
- The `docs/img/explore.png` screenshot was not retaken.

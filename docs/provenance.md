# Data provenance

Every corpus records the exact acquisition command, the resulting filename, byte size, and
`shasum -a 256`. A row whose text cannot be traced to a byte range in the downloaded source is a bug.

> Populated. Every checksum and byte count below came from a command that ran; the commands are shown alongside; do not write a checksum you
> have not computed.

## MAUD — Merger Agreement Understanding Dataset

- Source: https://www.atticusprojectai.org/maud · https://github.com/TheAtticusProject/maud
- License: CC BY 4.0 — attribution required
- Contents: 152 merger agreements, 47,000+ expert annotations, 92 ABA Public Target Deal Points
- Attribution: MAUD, The Atticus Project, CC BY 4.0.
- Command (run 2026-07-30) — `scripts/download_maud.sh`, which is:
  ```
  curl -sfL -o data/maud/data.zip \
    https://raw.githubusercontent.com/The-Atticus-Project/maud/main/data.zip
  unzip -qn data/maud/data.zip -d data/maud
  ```
- File: `data/maud/data.zip`
- Bytes: 32,893,590 (`wc -c`)
- sha256: `75af5a33d038e9254864f043da38072490ffe11e8488d58d0a2dd39c8f554519`
  (`shasum -a 256 data/maud/data.zip`)
- Extracted: 158 files, 202,424 KiB — 152 `data/contracts/contract_*.txt` (53,464 KiB),
  three label CSVs (`MAUD_train.csv` 81,299,409 B, `MAUD_dev.csv` 21,189,496 B,
  `MAUD_test.csv` 20,550,295 B) and `data/raw/{main,abridged,counterfactual}.csv`.
- Label rows across the three CSVs: 39,231, covering **152** contracts and **92** distinct
  `question` values — the ABA deal points.

> **Not** taken from the Hugging Face mirror `theatticusproject/maud`. That mirror carries the
> same label CSVs but only **100** of the 152 contract texts, and a matter whose text is
> missing cannot satisfy the mandatory drill-through to source clauses.

## CUAD — removed

CUAD (the Contract Understanding Atticus Dataset) was ingested into a `clauses` table until
#40. It was dropped because nothing queried it: 13,823 rows, every one `corpus='cuad'` with a
NULL `matter_id`, excluded from every facet by design and reachable only through the raw
Tables view. The ingest step, the table and the download script are gone. If clause-level
data comes back it comes back with a consumer, and its provenance block returns here with it.

## FOLIO — evaluated 2026-07-30, removed 2026-09-05 (#49)

FOLIO (Federated Open Legal Information Ontology, ALEA Institute, CC BY) was downloaded from
`https://github.com/alea-institute/FOLIO` — `FOLIO.owl`, 18,335,854 bytes, sha256
`44657b4ed844f5f9c9c48869184606b4fc671471a8263d79d241de87809fa239` — parsed with rdflib and
loaded whole: **18,259 concepts and 47,523 aliases**, hierarchy denormalized into three
ancestry columns. Measured against this corpus, **14 of those 18,259 concepts were used**, and
all 14 sit at the same level, so the descendant roll-up returned exactly what an equality match
returned. The hierarchy earned nothing here.

What the ontology *was* earning is one property: a stable code to join on instead of a display
label, so that "Health Care Industry" retitled to "Healthcare" cannot silently return zero rows
and read as *we have no comparable deals*. That property is delivered in full by
`data/mappings/sic_to_folio.csv` below, so #49 replaced the ontology with a 20-row
`industries(code, label)` table seeded from that file and dropped the loader, the two tables,
the `rdflib` dependency and the OWL parse on every ingest.

The industry codes still in the crosswalk are FOLIO IRI suffixes — that is where the vocabulary
came from, and the attribution stands: FOLIO is published by the ALEA Institute under CC BY 4.0.
This paragraph is the only place FOLIO is named as a thing that existed here.

## SEC EDGAR

- Source: https://www.sec.gov/edgar — free, public. Requires a descriptive User-Agent; respect rate limits.
- Used for: SIC industry code, deal value, signing/closing dates, party names, for the MAUD agreements
- Note: fetched per-CIK for a known set (no crawler). Record the fetch date — filings are amended.

## SEC EDGAR — enrichment (#9)

- Source: https://www.sec.gov/Archives/edgar/cik-lookup-data.txt (company-name → CIK index)
  and https://data.sec.gov/submissions/CIK##########.json (per-company SIC).
- Licence: US government work, public domain. SEC requires a descriptive User-Agent on
  automated requests; ours is
  `Clause Explorer research (open source; contact alex4334johnson@gmail.com)`.
- Rate limit used: **5 requests/second** (SEC fair-access guidance is 10/s).
- Command (run 2026-07-30) — `scripts/download_edgar_index.sh`:
  ```
  curl -sfL -A "<user agent>" -o data/edgar/cik-lookup-data.txt \
    https://www.sec.gov/Archives/edgar/cik-lookup-data.txt
  ```
- File: `data/edgar/cik-lookup-data.txt`
- Bytes: 39,865,365 · lines: 1,052,920
- sha256: `e3b9d73e3a3d696029b08a3b3589a6495cdcede98a3f70fdd832e1a6c25ca1fd`
- **Fetch date: 2026-07-30.** Filings get amended, so every submissions response is cached
  under `data/edgar/cache/` and never re-fetched; refreshing is an explicit `rm -rf` of that
  directory. 142 company-submission responses cached on this run.
- Derived file, checked in: `data/mappings/sic_to_folio.csv` — the SIC → industry crosswalk,
  **99 data rows** (`grep -c '^[0-9]' data/mappings/sic_to_folio.csv`) resolving to **20
  distinct industries**, curated from the SIC division structure against a set of
  NAICS-aligned industry concepts. Since #49 this file is also the seed for the `industries`
  table, written by the EDGAR ingest step before it assigns any code.

### Crosswalk coverage (#9)

Of the 152 matters, 139 resolved to an SEC-assigned SIC code, spanning **63 distinct SIC
codes**. The crosswalk resolves **63 of 63 — 100%** of the codes actually present, so every
matter that got an SIC also got an industry. Coverage of SIC space as a whole is *not* 100% and
is not claimed to be: the file maps the codes this corpus contains, longest-prefix first, and a
code it does not cover produces `NULL`, never a default bucket.

### Enrichment coverage (#9) — measured, not estimated

Re-counted on 2026-09-05 against a full re-ingest under the #49 schema, in an isolated
`explorer_49` database:

```sql
SELECT count(*), count(industry_code), count(signing_date),
       count(target_name), count(acquirer_name), count(sic_code), count(deal_value_usd)
FROM matters;
```

| field | resolved | of |
|---|---|---|
| `signing_date` | 149 | 152 |
| `target_name` | 143 | 152 |
| `sic_code` | 139 | 152 |
| `industry_code` | 139 | 152 |
| `acquirer_name` | 125 | 152 |
| `deal_value_usd` | **0** | 152 |

`is_inferred_industry` is TRUE on exactly the 139 rows that have an industry and FALSE on the
13 that do not — no row carries an industry without the inference flag, and none carries the
flag without an industry. The 139/13 split is unchanged by #49: the codes come from the same
crosswalk rows they always did, only the table they point at is different.

**`deal_value_usd` is unpopulated and this is a source limitation, not an oversight.** EDGAR's
company-submissions endpoint — the only endpoint this ingest touches — carries SIC, name and
state of incorporation. It does not carry transaction value. Stated consideration lives in the
*text* of the agreement, and extracting it would be an inference over prose rather than a
lookup, which is a different kind of claim and a different failure mode. `deal_value_usd`,
`deal_size_band` and `is_inferred_deal_value` therefore stay NULL/FALSE on all 152 rows rather
than carrying a plausible guess. Tracked separately; see the successor issue to #9.

Re-runs make no network calls: the most recent `ingest_runs` row for `edgar` records
`0 fetches` against 152 rows read, served entirely from `data/edgar/cache/`.

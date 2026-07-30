# Data provenance

Every corpus records the exact acquisition command, the resulting filename, byte size, and
`shasum -a 256`. A row whose text cannot be traced to a byte range in the downloaded source is a bug.

> Nothing below is filled in yet. Populated by the ingest issues; do not write a checksum you
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

## CUAD — Contract Understanding Atticus Dataset

- Source: https://www.atticusprojectai.org/cuad · https://github.com/TheAtticusProject/cuad
- License: CC BY 4.0
- Contents: commercial contracts, 41 expert-annotated clause categories
- Command / file / bytes / sha256: _not yet recorded_

## FOLIO — Federated Open Legal Information Ontology

- Source: https://github.com/alea-institute/FOLIO
- License: CC BY
- Contents: 18,000+ legal concepts, OWL
- Attribution: FOLIO is published by the ALEA Institute under CC BY 4.0.
- Command (run 2026-07-30):
  ```
  curl -sL -o data/folio/FOLIO.owl \
    https://raw.githubusercontent.com/alea-institute/FOLIO/main/FOLIO.owl
  ```
- File: `data/folio/FOLIO.owl`
- Bytes: 18,335,854 (`ls -l`)
- sha256: `44657b4ed844f5f9c9c48869184606b4fc671471a8263d79d241de87809fa239`
  (`shasum -a 256 data/folio/FOLIO.owl`)
- Loaded by `python -m explorer.ingest.folio` → 18,259 concepts, 47,523 aliases. The file
  declares 18,327 `owl:Class` nodes; the difference is unlabelled classes and the
  DEPRECATED / SANDBOX subtrees, which are excluded deliberately (see
  `backend/explorer/folio/loader.py`).

## SEC EDGAR

- Source: https://www.sec.gov/edgar — free, public. Requires a descriptive User-Agent; respect rate limits.
- Used for: SIC industry code, deal value, signing/closing dates, party names, for the MAUD agreements
- Note: fetched per-CIK for a known set (no crawler). Record the fetch date — filings are amended.

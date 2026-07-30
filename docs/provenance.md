# Data provenance

Every corpus records the exact acquisition command, the resulting filename, byte size, and
`shasum -a 256`. A row whose text cannot be traced to a byte range in the downloaded source is a bug.

> Nothing below is filled in yet. Populated by the ingest issues; do not write a checksum you
> have not computed.

## MAUD — Merger Agreement Understanding Dataset

- Source: https://www.atticusprojectai.org/maud · https://github.com/TheAtticusProject/maud
- License: CC BY 4.0 — attribution required
- Contents: 152 merger agreements, 47,000+ expert annotations, 92 ABA Public Target Deal Points
- Command: _not yet recorded_
- File / bytes / sha256: _not yet recorded_

## CUAD — Contract Understanding Atticus Dataset

- Source: https://www.atticusprojectai.org/cuad · https://github.com/TheAtticusProject/cuad
- License: CC BY 4.0
- Contents: commercial contracts, 41 expert-annotated clause categories
- Command / file / bytes / sha256: _not yet recorded_

## FOLIO — Federated Open Legal Information Ontology

- Source: https://github.com/alea-institute/FOLIO
- License: CC BY
- Contents: 18,000+ legal concepts, OWL
- Command / file / bytes / sha256: _not yet recorded_

## SEC EDGAR

- Source: https://www.sec.gov/edgar — free, public. Requires a descriptive User-Agent; respect rate limits.
- Used for: SIC industry code, deal value, signing/closing dates, party names, for the MAUD agreements
- Note: fetched per-CIK for a known set (no crawler). Record the fetch date — filings are amended.

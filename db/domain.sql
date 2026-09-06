-- Columns this corpus has that the spine does not name.
--
-- Applied by `quorum migrate` AFTER quorum's spine.sql, which is why every statement here is an
-- ALTER rather than a CREATE: the table already exists and belongs to the platform.
--
-- These could have gone in `records.attributes` as JSONB and needed no file at all. They are
-- columns because the facet query filters on three of them TOGETHER — category, size band and
-- date — and a composite index over three JSONB expressions is a worse answer than an index
-- over three columns when the shape is already known. A new domain that has not decided its
-- shape yet should use `attributes` and skip this file entirely.

-- Enrichment from EDGAR. NULL where unresolved, never guessed.
ALTER TABLE records ADD COLUMN IF NOT EXISTS deal_value_usd NUMERIC(18, 2);
ALTER TABLE records ADD COLUMN IF NOT EXISTS deal_size_band TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS signing_date   DATE;
ALTER TABLE records ADD COLUMN IF NOT EXISTS acquirer_name  TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS target_name    TEXT;
ALTER TABLE records ADD COLUMN IF NOT EXISTS sic_code       TEXT;

-- One flag per field that can be classifier output rather than gold. Industry codes come from a
-- SIC crosswalk and are inference; presenting them as ground truth is the largest source of
-- quiet error in this product, so the distinction lives in the schema and survives into the UI.
ALTER TABLE records ADD COLUMN IF NOT EXISTS is_inferred_industry   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE records ADD COLUMN IF NOT EXISTS is_inferred_deal_value BOOLEAN NOT NULL DEFAULT FALSE;

-- The facet query filters on these three together. This index is the reason they are columns.
DROP INDEX IF EXISTS idx_records_facets;
CREATE INDEX IF NOT EXISTS idx_records_facets
    ON records (category_code, deal_size_band, signing_date);

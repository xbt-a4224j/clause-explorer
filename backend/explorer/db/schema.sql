-- Clause Explorer schema.
--
-- Two shape decisions carry the whole design:
--
-- 1. deal_points is LONG (one row per matter x deal point), never wide. MAUD ships 92 deal
--    points and the ABA study revises them; wide would make each addition a migration + a
--    Cube model edit + a UI change. Long makes it rows, and lets deal_point_name be a Cube
--    dimension so new values appear in the product automatically.
--
-- 2. Inferred values are marked in the schema, not just in documentation. FOLIO
--    industry/service codes are classifier output, not label data. Without an is_inferred_*
--    flag they are indistinguishable from MAUD's expert gold labels, and every downstream
--    aggregate silently mixes the two.
--
-- updated_at exists on every table because Cube's refresh_key (#14) is
-- `SELECT MAX(updated_at)`. A table without it goes permanently stale in the semantic layer.
--
-- Removals. This file is applied idempotently rather than as a revision chain (see
-- db/migrate.py), so a table that leaves the model has to be dropped here or it survives
-- forever on every database that already ran an earlier version.
--
-- #40 dropped `clauses`. It held CUAD only — 13,823 rows, every one corpus='cuad' with a
-- NULL matter_id, written by one ingest step and read by no endpoint. An emptied table left
-- in place would still be a Tables-view row and a thing to explain, so the table goes with
-- the corpus. If clause-level storage returns it comes back as a table with a consumer.
DROP TABLE IF EXISTS clauses CASCADE;

CREATE TABLE IF NOT EXISTS folio_concepts (
    code            TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    parent_code     TEXT REFERENCES folio_concepts (code) ON DELETE SET NULL,
    level           SMALLINT NOT NULL DEFAULT 1,
    definition      TEXT,
    -- denormalized ancestry: Cube dimensions read these directly rather than walking a
    -- recursive CTE per facet query (#13)
    level_1_code    TEXT,
    level_2_code    TEXT,
    level_3_code    TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_folio_parent ON folio_concepts (parent_code);
CREATE INDEX IF NOT EXISTS idx_folio_level2 ON folio_concepts (level_2_code);
-- lowercased label lookup for resolve() (#6); the ontology is loaded once and read constantly
CREATE INDEX IF NOT EXISTS idx_folio_label_lower ON folio_concepts (lower(label));

-- skos:altLabel, kept out of folio_concepts because it is many-per-concept. resolve() checks
-- the exact label first and only then aliases, and refuses an alias that maps to more than one
-- concept rather than picking one (#6). FOLIO ships translated altLabels, so an alias table is
-- also where multilingual input gets resolved for free.
CREATE TABLE IF NOT EXISTS folio_aliases (
    alias       TEXT NOT NULL,
    code        TEXT NOT NULL REFERENCES folio_concepts (code) ON DELETE CASCADE,
    PRIMARY KEY (alias, code)
);
CREATE INDEX IF NOT EXISTS idx_folio_alias_lower ON folio_aliases (lower(alias));

CREATE TABLE IF NOT EXISTS matters (
    id                      TEXT PRIMARY KEY,
    -- provenance: every row must trace to a byte range in a downloaded file
    source_file             TEXT NOT NULL,
    source_contract_title   TEXT NOT NULL,
    corpus                  TEXT NOT NULL DEFAULT 'maud',

    -- enrichment from EDGAR (#9); NULL where unresolved, never guessed
    folio_industry_code     TEXT REFERENCES folio_concepts (code) ON DELETE SET NULL,
    folio_service_code      TEXT REFERENCES folio_concepts (code) ON DELETE SET NULL,
    deal_value_usd          NUMERIC(18, 2),
    deal_size_band          TEXT,
    signing_date            DATE,
    acquirer_name           TEXT,
    target_name             TEXT,
    sic_code                TEXT,

    -- inference flags, one per field that can be classifier output rather than gold
    is_inferred_industry    BOOLEAN NOT NULL DEFAULT FALSE,
    is_inferred_service     BOOLEAN NOT NULL DEFAULT FALSE,
    is_inferred_deal_value  BOOLEAN NOT NULL DEFAULT FALSE,

    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- facet queries filter on these three together (#13, #19)
CREATE INDEX IF NOT EXISTS idx_matters_facets
    ON matters (folio_industry_code, deal_size_band, signing_date);
CREATE INDEX IF NOT EXISTS idx_matters_corpus ON matters (corpus);

CREATE TABLE IF NOT EXISTS deal_points (
    id                  BIGSERIAL PRIMARY KEY,
    matter_id           TEXT NOT NULL REFERENCES matters (id) ON DELETE CASCADE,
    -- the dimension that makes this table extensible; NOT a column per deal point
    deal_point_name     TEXT NOT NULL,
    position            TEXT NOT NULL,          -- 'present' | 'absent' | free-text answer
    numeric_value       NUMERIC(18, 4),         -- e.g. reverse termination fee percent
    source_span_start   INTEGER,
    source_span_end     INTEGER,
    -- What the span IS, not merely that it exists (#43). 'anchored' = the characters at the
    -- span are the annotator's quoted answer text, found exactly once inside the recorded
    -- range. 'recorded' = MAUD's own envelope, i.e. where the answer was found; for a
    -- discontinuous annotation that includes provisions nobody quoted, which is why the
    -- drill-through renders a wide one as a labelled excerpt rather than as the clause.
    -- NULL = no span. A reader who cannot tell these apart will read an envelope as a clause.
    span_kind           TEXT,
    is_inferred         BOOLEAN NOT NULL DEFAULT FALSE,  -- FALSE for MAUD gold labels
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (matter_id, deal_point_name)
);
-- IF NOT EXISTS so an already-migrated database picks the column up without a reset.
ALTER TABLE deal_points ADD COLUMN IF NOT EXISTS span_kind TEXT;
-- The vocabulary and the invariant, in the schema rather than in a docstring: a span_kind
-- without a span (or a span without a kind) is a row nobody can interpret. NOT VALID so the
-- constraint governs every write from here on without failing on rows loaded before #43.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'deal_points_span_kind_ck') THEN
        ALTER TABLE deal_points ADD CONSTRAINT deal_points_span_kind_ck
            CHECK (
                (span_kind IS NULL AND source_span_start IS NULL)
                OR (span_kind IN ('anchored', 'recorded') AND source_span_start IS NOT NULL)
            ) NOT VALID;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_dp_name ON deal_points (deal_point_name);
CREATE INDEX IF NOT EXISTS idx_dp_matter ON deal_points (matter_id);

-- human labels from the Label tab (#29); feed re-calibration (#28)
CREATE TABLE IF NOT EXISTS labels (
    id                  BIGSERIAL PRIMARY KEY,
    target_kind         TEXT NOT NULL,          -- 'deal_point' | 'clause' | 'folio_industry'
    target_id           TEXT NOT NULL,
    field               TEXT NOT NULL,
    value               TEXT NOT NULL,
    prior_prediction    TEXT,
    labeller            TEXT NOT NULL DEFAULT 'local',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_labels_target ON labels (target_kind, target_id);

-- one row per ingest run so the Admin tab (#30) can show status without parsing logs
CREATE TABLE IF NOT EXISTS ingest_runs (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    rows_read       INTEGER NOT NULL DEFAULT 0,
    rows_upserted   INTEGER NOT NULL DEFAULT 0,
    duration_ms     NUMERIC(12, 1),
    sha256          TEXT,
    status          TEXT NOT NULL DEFAULT 'ok',
    detail          TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingest_source ON ingest_runs (source, started_at DESC);

-- updated_at must advance on write or Cube's refresh_key never invalidates.
--
-- clock_timestamp(), not now(): now() returns TRANSACTION start time and is constant for
-- the whole transaction, so an insert followed by an update in one transaction would leave
-- updated_at unchanged. Ingest does exactly that, which would leave Cube serving stale
-- aggregates with no way to notice.
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['folio_concepts','matters','deal_points','labels','ingest_runs']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%1$s ON %1$s', t);
        EXECUTE format(
            'CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t);
    END LOOP;
END $$;

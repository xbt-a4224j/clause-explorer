-- Clause Explorer schema.
--
-- Two shape decisions carry the whole design:
--
-- 1. deal_points is LONG (one row per matter x deal point), never wide. MAUD ships 92 deal
--    points and the ABA study revises them; wide would make each addition a migration + a
--    Cube model edit + a UI change. Long makes it rows, and lets deal_point_name be a Cube
--    dimension so new values appear in the product automatically.
--
-- 2. Inferred values are marked in the schema, not just in documentation. CUAD ships no
--    industry metadata, so FOLIO industry/service codes are classifier output. Without an
--    is_inferred_* flag they are indistinguishable from MAUD's expert gold labels, and every
--    downstream aggregate silently mixes the two.
--
-- updated_at exists on every table because Cube's refresh_key (#14) is
-- `SELECT MAX(updated_at)`. A table without it goes permanently stale in the semantic layer.

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
    is_inferred         BOOLEAN NOT NULL DEFAULT FALSE,  -- FALSE for MAUD gold labels
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (matter_id, deal_point_name)
);
CREATE INDEX IF NOT EXISTS idx_dp_name ON deal_points (deal_point_name);
CREATE INDEX IF NOT EXISTS idx_dp_matter ON deal_points (matter_id);

CREATE TABLE IF NOT EXISTS clauses (
    id                  TEXT PRIMARY KEY,
    matter_id           TEXT REFERENCES matters (id) ON DELETE CASCADE,
    corpus              TEXT NOT NULL DEFAULT 'cuad',
    clause_type         TEXT NOT NULL,          -- CUAD category: expert gold label
    text                TEXT NOT NULL,
    source_file         TEXT NOT NULL,
    char_start          INTEGER NOT NULL,
    char_end            INTEGER NOT NULL,
    folio_industry_code TEXT REFERENCES folio_concepts (code) ON DELETE SET NULL,
    is_inferred_industry BOOLEAN NOT NULL DEFAULT TRUE,  -- CUAD ships no industry metadata
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_clauses_type ON clauses (clause_type);
CREATE INDEX IF NOT EXISTS idx_clauses_matter ON clauses (matter_id);

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
    FOREACH t IN ARRAY ARRAY['folio_concepts','matters','deal_points','clauses','labels','ingest_runs']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%1$s ON %1$s', t);
        EXECUTE format(
            'CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t);
    END LOOP;
END $$;

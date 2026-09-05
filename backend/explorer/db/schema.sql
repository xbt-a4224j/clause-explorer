-- Clause Explorer schema.
--
-- Two shape decisions carry the whole design:
--
-- 1. deal_points is LONG (one row per matter x deal point), never wide. MAUD ships 92 deal
--    points and the ABA study revises them; wide would make each addition a migration + a
--    Cube model edit + a UI change. Long makes it rows, and lets deal_point_name be a Cube
--    dimension so new values appear in the product automatically.
--
-- 2. Inferred values are marked in the schema, not just in documentation. Industry codes
--    come from the SIC crosswalk, so they are classifier output, not label data. Without an
--    is_inferred_* flag they are indistinguishable from MAUD's expert gold labels, and every
--    downstream aggregate silently mixes the two.
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

-- #49 dropped the ontology the same way. It loaded 18,259 concepts and the corpus used 14,
-- all of them at the same level, so the hierarchy walk returned exactly what an equality
-- match returned. What it was actually earning is the one line below: a stable code to join
-- on, so a label drifting from "Health Care Industry" to "Healthcare" cannot silently return
-- zero rows and read as "we have no comparable deals". The crosswalk already delivers that.
DROP TABLE IF EXISTS folio_aliases CASCADE;
-- CASCADE on folio_concepts drops the foreign-key CONSTRAINT on matters, not the column, so
-- the data survives the drop and the rename below re-points it at the new table.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'matters'
          AND column_name = 'folio_industry_code'
    ) THEN
        ALTER TABLE matters RENAME COLUMN folio_industry_code TO industry_code;
    END IF;
    -- folio_service_code and is_inferred_service went with the ontology: a second FOLIO
    -- branch was never loaded, never written and never read, and the column's foreign key
    -- pointed at a table that no longer exists.
    ALTER TABLE IF EXISTS matters DROP COLUMN IF EXISTS folio_service_code;
    ALTER TABLE IF EXISTS matters DROP COLUMN IF EXISTS is_inferred_service;
END $$;
DROP TABLE IF EXISTS folio_concepts CASCADE;

-- The industry vocabulary the product actually facets on: one row per distinct code in
-- data/mappings/sic_to_folio.csv, seeded by the EDGAR ingest step that assigns the codes.
--
-- `code` is opaque and stable; `label` is display text and may be retitled. Everything that
-- filters joins on `code`. That is the whole reason this table exists rather than storing the
-- label on `matters` directly — see #25 for what a label-keyed filter does when it drifts.
CREATE TABLE IF NOT EXISTS industries (
    code        TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- lowercased label lookup for the exact tier of filter-value resolution (#25)
CREATE INDEX IF NOT EXISTS idx_industries_label_lower ON industries (lower(label));

CREATE TABLE IF NOT EXISTS matters (
    id                      TEXT PRIMARY KEY,
    -- provenance: every row must trace to a byte range in a downloaded file
    source_file             TEXT NOT NULL,
    source_contract_title   TEXT NOT NULL,
    corpus                  TEXT NOT NULL DEFAULT 'maud',

    -- enrichment from EDGAR (#9); NULL where unresolved, never guessed
    industry_code           TEXT REFERENCES industries (code) ON DELETE SET NULL,
    deal_value_usd          NUMERIC(18, 2),
    deal_size_band          TEXT,
    signing_date            DATE,
    acquirer_name           TEXT,
    target_name             TEXT,
    sic_code                TEXT,

    -- inference flags, one per field that can be classifier output rather than gold
    is_inferred_industry    BOOLEAN NOT NULL DEFAULT FALSE,
    is_inferred_deal_value  BOOLEAN NOT NULL DEFAULT FALSE,

    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- A database migrated before #49 already has `matters`, so CREATE TABLE IF NOT EXISTS is a
-- no-op there and the renamed column carries no foreign key. NOT VALID: the codes already in
-- the column are crosswalk codes and the seed writes all of them, but the seed runs at ingest
-- and this runs at migrate, so validating here would fail on ordering rather than on data.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'matters_industry_code_fkey') THEN
        ALTER TABLE matters ADD CONSTRAINT matters_industry_code_fkey
            FOREIGN KEY (industry_code) REFERENCES industries (code) ON DELETE SET NULL
            NOT VALID;
    END IF;
END $$;
-- facet queries filter on these three together (#13, #19)
DROP INDEX IF EXISTS idx_matters_facets;
CREATE INDEX IF NOT EXISTS idx_matters_facets
    ON matters (industry_code, deal_size_band, signing_date);
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
    target_kind         TEXT NOT NULL,          -- 'deal_point' | 'clause' | 'industry'
    target_id           TEXT NOT NULL,
    field               TEXT NOT NULL,
    value               TEXT NOT NULL,
    prior_prediction    TEXT,
    labeller            TEXT NOT NULL DEFAULT 'local',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_labels_target ON labels (target_kind, target_id);

-- Chip corrections from the Ask tab (#51): a labelled disagreement with the model.
--
-- One row per confirmed selection — what the model returned, what the person ran, and which
-- parts they changed. `agreed` rows are recorded too: an eval that only stores corrections
-- learns only what the model got wrong, and "it was right and nobody touched it" is the other
-- half of an accuracy figure.
--
-- Written ONLY by a human confirming or editing on Ask. `/agent/ask` never writes here. A
-- model that wrote its own eval data would be recording an opinion it already held rather
-- than evidence against it.
--
-- JSONB, not a normalized selection schema: the shape is Cube's query object, it is already
-- versioned by cube/model/*.yml, and shredding it into rows would create a second definition
-- of what a selection is — the one that goes stale when the Cube model changes.
CREATE TABLE IF NOT EXISTS selection_corrections (
    id                  BIGSERIAL PRIMARY KEY,
    question            TEXT NOT NULL,
    model_selection     JSONB NOT NULL,
    confirmed_selection JSONB NOT NULL,
    -- 'measures' | 'dimensions' | 'filters'; empty on an agreement
    changed_fields      TEXT[] NOT NULL DEFAULT '{}',
    agreed              BOOLEAN NOT NULL,
    labeller            TEXT NOT NULL DEFAULT 'local',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_selection_corrections_agreed
    ON selection_corrections (agreed, created_at DESC);

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
    FOREACH t IN ARRAY ARRAY['industries','matters','deal_points','labels','ingest_runs','selection_corrections']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_touch_%1$s ON %1$s', t);
        EXECUTE format(
            'CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$s '
            'FOR EACH ROW EXECUTE FUNCTION touch_updated_at()', t);
    END LOOP;
END $$;

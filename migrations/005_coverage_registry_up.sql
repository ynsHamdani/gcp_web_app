-- Migration 005: versioned polygon coverage-layer registry and features.
-- Requires migrations 003_admin_production and 004_gcp_semantic_context.
-- Additive only: existing GCP, context, raster-layer and settings tables are untouched.

BEGIN;

-- Keep a lightweight migration ledger for this app. Earlier database setup
-- scripts did not consistently create this table, so migration 005 ensures it.
CREATE TABLE IF NOT EXISTS gcp_schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- PostGIS is shared infrastructure; this migration does not remove it on rollback.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS coverage_layers (
    coverage_layer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    layer_name        VARCHAR(160) NOT NULL,
    version           INTEGER NOT NULL,
    source_filename   VARCHAR(255) NOT NULL,
    source_format     VARCHAR(24) NOT NULL,
    source_layer_name VARCHAR(255) NOT NULL DEFAULT '',
    source_crs        TEXT NOT NULL,
    target_srid       INTEGER NOT NULL DEFAULT 25832,
    geometry_type     VARCHAR(32) NOT NULL DEFAULT 'MULTIPOLYGON',
    feature_count     BIGINT NOT NULL,
    source_sha256     CHAR(64) NOT NULL,
    notes             TEXT NOT NULL DEFAULT '',
    imported_by       BIGINT NULL REFERENCES users(user_id)
                      ON UPDATE CASCADE ON DELETE SET NULL,
    imported_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_coverage_layers_name
        CHECK (length(btrim(layer_name)) BETWEEN 2 AND 160),
    CONSTRAINT ck_coverage_layers_version
        CHECK (version >= 1),
    CONSTRAINT ck_coverage_layers_format
        CHECK (source_format IN ('gpkg', 'geojson', 'shapefile_zip')),
    CONSTRAINT ck_coverage_layers_target_srid
        CHECK (target_srid = 25832),
    CONSTRAINT ck_coverage_layers_geometry_type
        CHECK (geometry_type = 'MULTIPOLYGON'),
    CONSTRAINT ck_coverage_layers_feature_count
        CHECK (feature_count > 0),
    CONSTRAINT ck_coverage_layers_sha256
        CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_coverage_layers_notes_length
        CHECK (length(notes) <= 2000)
);

-- Case-insensitive logical names, immutable numbered versions, one active version.
CREATE UNIQUE INDEX IF NOT EXISTS uq_coverage_layers_name_version
    ON coverage_layers (LOWER(layer_name), version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_coverage_layers_one_active_version
    ON coverage_layers (LOWER(layer_name))
    WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_coverage_layers_name_imported
    ON coverage_layers (LOWER(layer_name), imported_at DESC);

CREATE TABLE IF NOT EXISTS coverage_features (
    coverage_feature_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    coverage_layer_id   BIGINT NOT NULL REFERENCES coverage_layers(coverage_layer_id)
                        ON UPDATE CASCADE ON DELETE CASCADE,
    source_feature_key  VARCHAR(500) NOT NULL,
    feature_label       VARCHAR(500) NOT NULL,
    source_index        INTEGER NOT NULL,
    attributes          JSONB NOT NULL DEFAULT '{}'::jsonb,
    geom                geometry(MultiPolygon, 25832) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_coverage_features_source_key
        UNIQUE (coverage_layer_id, source_feature_key),
    CONSTRAINT ck_coverage_features_source_index
        CHECK (source_index >= 1),
    CONSTRAINT ck_coverage_features_valid_geom
        CHECK (NOT ST_IsEmpty(geom) AND ST_IsValid(geom))
);

CREATE INDEX IF NOT EXISTS idx_coverage_features_layer
    ON coverage_features (coverage_layer_id);
CREATE INDEX IF NOT EXISTS idx_coverage_features_geom
    ON coverage_features USING GIST (geom);

INSERT INTO gcp_schema_migrations (version)
VALUES ('005_coverage_registry')
ON CONFLICT (version) DO NOTHING;

COMMIT;

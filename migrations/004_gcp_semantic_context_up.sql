-- Phase 1: Semantic GCP Context
-- Target: authentication-rbac branch, PostgreSQL schema used by app1.py.
-- Safe rollout: run on a verified DEVELOPMENT database first.

BEGIN;

CREATE TABLE IF NOT EXISTS gcp_context_categories (
    context_category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code                VARCHAR(64) NOT NULL,
    label               VARCHAR(120) NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    is_system           BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order          INTEGER NOT NULL DEFAULT 100,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_gcp_context_categories_code UNIQUE (code),
    CONSTRAINT ck_gcp_context_categories_code
        CHECK (code ~ '^[A-Z][A-Z0-9_]{1,63}$'),
    CONSTRAINT ck_gcp_context_categories_sort_order
        CHECK (sort_order >= 0),
    CONSTRAINT ck_gcp_context_other_always_active
        CHECK (code <> 'OTHER' OR is_active = TRUE),
    CONSTRAINT ck_gcp_context_legacy_not_active
        CHECK (code <> 'LEGACY_UNRECORDED' OR is_active = FALSE)
);

INSERT INTO gcp_context_categories
    (code, label, description, is_active, is_system, sort_order)
VALUES
    ('ROAD_INTERSECTION', 'Road intersection', 'Intersection of two or more roads', TRUE, FALSE, 10),
    ('ROAD_BEND', 'Road bend', 'A distinctive change in road direction', TRUE, FALSE, 20),
    ('RIVER_CONFLUENCE', 'River confluence', 'Meeting point of two or more rivers', TRUE, FALSE, 30),
    ('RIVER_BEND', 'River bend / meander', 'A distinctive river curvature', TRUE, FALSE, 40),
    ('BRIDGE_CROSSING', 'Bridge / crossing', 'A bridge or crossing over a geographical feature', TRUE, FALSE, 50),
    ('BUILDING_CORNER', 'Building corner', 'A clearly identifiable building corner', TRUE, FALSE, 60),
    ('RAILWAY_CROSSING', 'Railway crossing', 'Intersection between railway and another transport route', TRUE, FALSE, 70),
    ('COASTLINE_FEATURE', 'Coastline feature', 'A distinctive coastal feature', TRUE, FALSE, 80),
    ('LAND_COVER_BOUNDARY', 'Land-cover boundary', 'Boundary between two identifiable land-cover types', TRUE, FALSE, 90),
    ('OTHER', 'Other / not identifiable', 'Use when the context is unknown, unclear or not represented by the available categories', TRUE, TRUE, 1000),
    ('LEGACY_UNRECORDED', 'Legacy – context not recorded', 'Reserved category for GCP records created before semantic context was collected', FALSE, TRUE, 2147483647)
ON CONFLICT (code) DO NOTHING;

-- Add nullable fields first so existing partitioned GCP data remains intact.
ALTER TABLE gcps
    ADD COLUMN IF NOT EXISTS context_category_id BIGINT,
    ADD COLUMN IF NOT EXISTS context_remark TEXT;

-- Assign only previously unannotated rows to the reserved legacy category.
UPDATE gcps AS g
SET context_category_id = c.context_category_id
FROM gcp_context_categories AS c
WHERE c.code = 'LEGACY_UNRECORDED'
  AND g.context_category_id IS NULL;

ALTER TABLE gcps
    ALTER COLUMN context_category_id SET NOT NULL;

-- Keep the previous application version operational during a coordinated
-- rollback: legacy code paths that omit context_category_id will be marked as
-- unrecorded instead of failing. The Phase 1 application always supplies an
-- explicit active category and never relies on this default for new GCPs.
DO $$
DECLARE
    legacy_category_id BIGINT;
BEGIN
    SELECT context_category_id
      INTO STRICT legacy_category_id
      FROM gcp_context_categories
     WHERE code = 'LEGACY_UNRECORDED';
    EXECUTE format(
        'ALTER TABLE gcps ALTER COLUMN context_category_id SET DEFAULT %s',
        legacy_category_id
    );
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_gcps_context_remark_length'
          AND conrelid = 'gcps'::regclass
    ) THEN
        ALTER TABLE gcps
            ADD CONSTRAINT ck_gcps_context_remark_length
            CHECK (context_remark IS NULL OR length(context_remark) <= 2000);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_gcps_context_category'
          AND conrelid = 'gcps'::regclass
    ) THEN
        ALTER TABLE gcps
            ADD CONSTRAINT fk_gcps_context_category
            FOREIGN KEY (context_category_id)
            REFERENCES gcp_context_categories (context_category_id)
            ON UPDATE RESTRICT
            ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_gcps_context_category
    ON gcps (context_category_id);

CREATE INDEX IF NOT EXISTS idx_gcp_context_categories_active_order
    ON gcp_context_categories (is_active, sort_order, label);

COMMIT;

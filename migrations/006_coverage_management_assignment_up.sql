-- Migration 006: coverage lifecycle controls and idempotent publication.
-- Requires 005_coverage_registry. Additive only; GCP tables are untouched.

BEGIN;

ALTER TABLE coverage_layers
    ADD COLUMN IF NOT EXISTS is_suppressed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS publish_token UUID,
    ADD COLUMN IF NOT EXISTS extent geometry(Polygon, 25832);

-- Persist the overall extent once, so opening/zooming to a layer does not scan
-- every polygon feature again. Existing versions are backfilled in-place.
UPDATE coverage_layers AS l
SET extent = e.layer_extent
FROM (
    SELECT coverage_layer_id,
           ST_SetSRID(ST_Envelope(ST_Extent(geom)), 25832) AS layer_extent
    FROM coverage_features
    GROUP BY coverage_layer_id
) AS e
WHERE e.coverage_layer_id = l.coverage_layer_id
  AND l.extent IS NULL;

-- A publication token makes a retried request return the already-created
-- version instead of inserting the same data twice.
CREATE UNIQUE INDEX IF NOT EXISTS uq_coverage_layers_publish_token
    ON coverage_layers (publish_token)
    WHERE publish_token IS NOT NULL;

-- Keep the existing B-tree layer index and GiST geometry index from migration
-- 005. This composite B-tree helps registry-scoped feature paging/exports.
CREATE INDEX IF NOT EXISTS idx_coverage_features_layer_feature
    ON coverage_features (coverage_layer_id, coverage_feature_id);

INSERT INTO gcp_schema_migrations (version)
VALUES ('006_coverage_management_assignment')
ON CONFLICT (version) DO NOTHING;

COMMIT;

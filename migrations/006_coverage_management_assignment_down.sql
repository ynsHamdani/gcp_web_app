-- Migration 006 rollback.
-- This removes lifecycle/idempotency metadata only. Coverage features and
-- coverage layers are preserved. Suppression states are not recoverable after
-- dropping is_suppressed; review/reconcile those versions before rollback.

BEGIN;

DROP INDEX IF EXISTS idx_coverage_features_layer_feature;
DROP INDEX IF EXISTS uq_coverage_layers_publish_token;
ALTER TABLE coverage_layers DROP COLUMN IF EXISTS publish_token;
ALTER TABLE coverage_layers DROP COLUMN IF EXISTS is_suppressed;
ALTER TABLE coverage_layers DROP COLUMN IF EXISTS extent;
DELETE FROM gcp_schema_migrations
WHERE version = '006_coverage_management_assignment';

COMMIT;

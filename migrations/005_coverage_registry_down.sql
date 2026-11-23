-- Rollback for migration 005_coverage_registry.
-- Imported coverage data is deleted. The shared PostGIS extension is retained.

BEGIN;

DROP TABLE IF EXISTS coverage_features;
DROP TABLE IF EXISTS coverage_layers;

DELETE FROM gcp_schema_migrations
WHERE version = '005_coverage_registry';

COMMIT;

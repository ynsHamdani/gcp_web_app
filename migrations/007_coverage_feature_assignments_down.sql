-- Migration 007 rollback: removes work-allocation relationships only.
-- Coverage layers and features remain intact; assignment rows are removed.

BEGIN;

DROP TABLE IF EXISTS coverage_feature_assignments;
DELETE FROM gcp_schema_migrations
WHERE version = '007_coverage_feature_assignments';

COMMIT;

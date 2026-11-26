-- Migration 008 rollback: removes polygon task objectives and instructions.
-- This does not remove polygon-to-student assignments, coverage features or GCPs.
-- Export task text first if it needs to be retained outside the application.

BEGIN;

DROP TABLE IF EXISTS coverage_feature_tasks;
DELETE FROM gcp_schema_migrations
WHERE version = '008_coverage_feature_tasks';

COMMIT;

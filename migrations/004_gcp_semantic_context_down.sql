-- Rollback for Phase 1: Semantic GCP Context.
-- WARNING: this drops all collected semantic annotations. Export them first
-- if this migration has been used in a non-disposable environment.

BEGIN;

ALTER TABLE gcps
    DROP CONSTRAINT IF EXISTS fk_gcps_context_category,
    DROP CONSTRAINT IF EXISTS ck_gcps_context_remark_length;

DROP INDEX IF EXISTS idx_gcps_context_category;
DROP INDEX IF EXISTS idx_gcp_context_categories_active_order;

ALTER TABLE gcps
    DROP COLUMN IF EXISTS context_category_id,
    DROP COLUMN IF EXISTS context_remark;

DROP TABLE IF EXISTS gcp_context_categories;

COMMIT;

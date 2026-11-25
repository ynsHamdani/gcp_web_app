-- Migration 007: assign coverage polygons to one or more student accounts.
-- Additive only. Existing GCP collection and spatial-assignment rules are untouched.

BEGIN;

CREATE TABLE IF NOT EXISTS coverage_feature_assignments (
    coverage_feature_id BIGINT NOT NULL
        REFERENCES coverage_features (coverage_feature_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    student_id BIGINT NOT NULL
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    assigned_by BIGINT NULL
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_coverage_feature_assignments
        PRIMARY KEY (coverage_feature_id, student_id)
);

-- The primary key serves administrator feature -> student lookups. This
-- reverse index serves student -> assigned features/layers and map requests.
CREATE INDEX IF NOT EXISTS idx_coverage_feature_assignments_student_feature
    ON coverage_feature_assignments (student_id, coverage_feature_id);

INSERT INTO gcp_schema_migrations (version)
VALUES ('007_coverage_feature_assignments')
ON CONFLICT (version) DO NOTHING;

COMMIT;

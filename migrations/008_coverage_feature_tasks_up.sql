-- Migration 008: objective and instructions attached to a coverage feature.
-- One shared task per polygon; student-to-polygon relationships remain in
-- coverage_feature_assignments. Existing GCP tables and spatial rules are untouched.

BEGIN;

CREATE TABLE IF NOT EXISTS coverage_feature_tasks (
    coverage_feature_id BIGINT PRIMARY KEY
        REFERENCES coverage_features (coverage_feature_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    objective VARCHAR(240) NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    updated_by BIGINT NULL
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_coverage_feature_tasks_objective_length
        CHECK (char_length(objective) <= 240),
    CONSTRAINT ck_coverage_feature_tasks_instructions_length
        CHECK (char_length(instructions) <= 10000)
);

INSERT INTO gcp_schema_migrations (version)
VALUES ('008_coverage_feature_tasks')
ON CONFLICT (version) DO NOTHING;

COMMIT;

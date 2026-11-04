-- Migration 003: administration, persistent runtime settings and revocable sessions.
-- Run against the existing gcp_web_app database with psql.
-- Safe to re-run: additions and seed settings are idempotent.

BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

-- Prevent case-only duplicate usernames/emails. Stop rather than silently
-- altering an existing account if such duplicates are already present.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM users GROUP BY LOWER(username) HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Migration stopped: usernames contain case-insensitive duplicates. Resolve them before retrying.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM users GROUP BY LOWER(email) HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Migration stopped: emails contain case-insensitive duplicates. Resolve them before retrying.';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_lower
    ON users (LOWER(username));
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower
    ON users (LOWER(email));

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key  VARCHAR(100) PRIMARY KEY,
    setting_value JSONB NOT NULL,
    updated_by BIGINT NULL REFERENCES users(user_id) ON UPDATE CASCADE ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id_hash CHAR(64) PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    revoke_reason VARCHAR(100) NULL,
    user_agent VARCHAR(300) NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_expiry
    ON auth_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry
    ON auth_sessions (expires_at);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_active_last_seen
    ON auth_sessions (last_seen_at DESC)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS admin_audit_log (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id BIGINT NULL REFERENCES users(user_id) ON UPDATE CASCADE ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(80) NOT NULL,
    target_id VARCHAR(160) NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_created_at
    ON admin_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_actor
    ON admin_audit_log (actor_user_id, created_at DESC);

-- JSONB scalar values; these are the recommended initial defaults.
INSERT INTO app_settings (setting_key, setting_value)
VALUES
    ('raster_ttl_hours', '24'::jsonb),
    ('max_upload_size_mb', '256'::jsonb)
ON CONFLICT (setting_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS gcp_schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO gcp_schema_migrations (version)
VALUES ('003_admin_production')
ON CONFLICT (version) DO NOTHING;

COMMIT;

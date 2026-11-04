-- Migration 003 rollback.
-- WARNING: this removes session history, admin audit history and runtime settings.
-- Export/backup these tables first if those records must be retained.

BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE must_change_password = TRUE) THEN
        RAISE EXCEPTION 'Rollback stopped: one or more student accounts still require a first-login password change. Have those users change their temporary password before removing this migration.';
    END IF;
END $$;

DELETE FROM gcp_schema_migrations WHERE version = '003_admin_production';
DROP TABLE IF EXISTS admin_audit_log;
DROP TABLE IF EXISTS auth_sessions;
DROP TABLE IF EXISTS app_settings;
DROP INDEX IF EXISTS uq_users_username_lower;
DROP INDEX IF EXISTS uq_users_email_lower;
ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;

COMMIT;

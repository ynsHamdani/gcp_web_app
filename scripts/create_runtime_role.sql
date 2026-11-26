-- Create a restricted runtime login for the GCP Web App on Neon/PostgreSQL.
-- Run this once in the target database while connected as neondb_owner (or
-- another database role permitted to create roles and grant these privileges).
-- Replace the password below with a new, unique, high-entropy password first.
-- Do not reuse GCP_SECRET_KEY, RASTER_SIGNING_KEY, or the neondb_owner password.

DO $$
DECLARE
    runtime_password TEXT := 'kLm_1qgovewznh9Y';
BEGIN
    IF runtime_password LIKE 'REPLACE_WITH_%' OR length(runtime_password) < 32 THEN
        RAISE EXCEPTION 'Replace runtime_password with a unique password of at least 32 characters.';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gcp_app_runtime') THEN
        RAISE EXCEPTION 'Role gcp_app_runtime already exists. Inspect it and apply grants manually; this script will not reset its password.';
    END IF;

    EXECUTE format(
        'CREATE ROLE gcp_app_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
        runtime_password
    );
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO gcp_app_runtime', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO gcp_app_runtime;

-- Core application tables.
GRANT SELECT ON TABLE public.users TO gcp_app_runtime;
GRANT INSERT (username, email, password_hash, user_role, must_change_password)
    ON TABLE public.users TO gcp_app_runtime;
GRANT UPDATE (username, email, password_hash, is_active, must_change_password)
    ON TABLE public.users TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE public.layers TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.gcps TO gcp_app_runtime;

-- Authentication, runtime settings, and audit writes.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.auth_sessions TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE ON TABLE public.app_settings TO gcp_app_runtime;
GRANT INSERT ON TABLE public.admin_audit_log TO gcp_app_runtime;

-- Semantic GCP context and polygon allocation workflow.
GRANT SELECT, INSERT, UPDATE ON TABLE public.gcp_context_categories TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.coverage_layers TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.coverage_features TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.coverage_feature_assignments TO gcp_app_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.coverage_feature_tasks TO gcp_app_runtime;

-- Required by identity/serial-backed application inserts. This does not grant
-- table DDL, role management, or database ownership.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gcp_app_runtime;

-- Intentionally omitted: gcp_schema_migrations and schema/extension DDL.
-- Apply the corresponding table grants whenever a future application
-- migration introduces a new runtime table.

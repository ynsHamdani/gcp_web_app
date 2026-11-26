-- Migration 009 rollback is deliberately guarded.
-- It is only safe before bootstrap and before any Super Admin account exists.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.users WHERE user_role = 'super_admin') THEN
        RAISE EXCEPTION 'Cannot roll back Stage 2 while any Super Admin account exists.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.super_admin_bootstrap_guard
        WHERE bootstrap_completed_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Cannot roll back Stage 2 after Super Admin bootstrap has completed.';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gcp_app_runtime') THEN
        EXECUTE 'REVOKE UPDATE (user_role) ON TABLE public.users FROM gcp_app_runtime';
        EXECUTE 'GRANT INSERT (user_role) ON TABLE public.users TO gcp_app_runtime';
        EXECUTE 'REVOKE UPDATE (bootstrap_completed_at, bootstrapped_by, promoted_user_id) ON TABLE public.super_admin_bootstrap_guard FROM gcp_app_runtime';
        EXECUTE 'REVOKE SELECT ON TABLE public.super_admin_bootstrap_guard FROM gcp_app_runtime';
        EXECUTE 'REVOKE SELECT ON TABLE public.admin_audit_log FROM gcp_app_runtime';
    END IF;
END $$;

DROP INDEX IF EXISTS public.idx_users_active_super_admin;
DROP TABLE IF EXISTS public.super_admin_bootstrap_guard;
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS ck_users_user_role;
ALTER TABLE public.users ALTER COLUMN user_role DROP DEFAULT;
ALTER TABLE public.users
    ADD CONSTRAINT users_user_role_check CHECK (user_role IN ('student', 'admin'));
DELETE FROM public.gcp_schema_migrations WHERE version = '009_super_admin';

COMMIT;

-- Migration 009: Super Admin hierarchy and one-time bootstrap guard.
-- Run as the schema owner (for example neondb_owner), not as gcp_app_runtime.
-- Additive to user data, GCPs, coverage, assignments, and audit history.

BEGIN;

-- Replace the original two-role CHECK constraint without assuming its name.
DO $$
DECLARE
    item RECORD;
BEGIN
    FOR item IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.users'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%user_role%'
    LOOP
        EXECUTE format('ALTER TABLE public.users DROP CONSTRAINT %I', item.conname);
    END LOOP;
END $$;

ALTER TABLE public.users
    ADD CONSTRAINT ck_users_user_role
    CHECK (user_role IN ('student', 'admin', 'super_admin'));

-- Student is the safe default. The runtime role no longer needs INSERT access
-- to user_role; privileged creation inserts a student row and promotes it in
-- the same server-side transaction after verifying the Super Admin actor.
ALTER TABLE public.users ALTER COLUMN user_role SET DEFAULT 'student';

CREATE TABLE IF NOT EXISTS public.super_admin_bootstrap_guard (
    guard_id SMALLINT PRIMARY KEY CHECK (guard_id = 1),
    bootstrap_completed_at TIMESTAMPTZ NULL,
    bootstrapped_by BIGINT NULL REFERENCES public.users(user_id) ON UPDATE CASCADE ON DELETE SET NULL,
    promoted_user_id BIGINT NULL REFERENCES public.users(user_id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT ck_super_admin_bootstrap_guard_state CHECK (
        (bootstrap_completed_at IS NULL AND bootstrapped_by IS NULL AND promoted_user_id IS NULL)
        OR
        (bootstrap_completed_at IS NOT NULL AND bootstrapped_by IS NOT NULL AND promoted_user_id IS NOT NULL)
    )
);

INSERT INTO public.super_admin_bootstrap_guard (guard_id)
VALUES (1)
ON CONFLICT (guard_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_users_active_super_admin
    ON public.users (user_id)
    WHERE user_role = 'super_admin' AND is_active = TRUE;

INSERT INTO public.gcp_schema_migrations (version)
VALUES ('009_super_admin')
ON CONFLICT (version) DO NOTHING;

-- The Stage 1 runtime role intentionally lacked permission to change roles.
-- Grant only the additional columns/table operations required by Stage 2.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gcp_app_runtime') THEN
        EXECUTE 'REVOKE INSERT (user_role) ON TABLE public.users FROM gcp_app_runtime';
        EXECUTE 'GRANT UPDATE (user_role) ON TABLE public.users TO gcp_app_runtime';
        EXECUTE 'GRANT SELECT ON TABLE public.super_admin_bootstrap_guard TO gcp_app_runtime';
        EXECUTE 'GRANT UPDATE (bootstrap_completed_at, bootstrapped_by, promoted_user_id) ON TABLE public.super_admin_bootstrap_guard TO gcp_app_runtime';
        EXECUTE 'GRANT SELECT ON TABLE public.admin_audit_log TO gcp_app_runtime';
    END IF;
END $$;

COMMIT;

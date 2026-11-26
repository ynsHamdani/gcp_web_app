from __future__ import annotations

from pathlib import Path

from auth.permissions import ALL_ROLES, is_admin_role, is_super_admin_role

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_role_hierarchy_has_three_roles_and_super_admin_inherits_admin_access():
    assert ALL_ROLES == frozenset({"student", "admin", "super_admin"})
    assert is_admin_role("admin")
    assert is_admin_role("super_admin")
    assert not is_admin_role("student")
    assert is_super_admin_role("super_admin")
    assert not is_super_admin_role("admin")


def test_migration_adds_third_role_and_one_time_bootstrap_guard():
    up = read("migrations/009_super_admin_up.sql")
    assert "'student', 'admin', 'super_admin'" in up
    assert "CREATE TABLE IF NOT EXISTS public.super_admin_bootstrap_guard" in up
    assert "bootstrap_completed_at" in up
    assert "INSERT INTO public.super_admin_bootstrap_guard (guard_id)" in up
    assert "GRANT SELECT ON TABLE public.super_admin_bootstrap_guard" in up
    assert "GRANT SELECT ON TABLE public.admin_audit_log" in up
    assert "GRANT UPDATE (bootstrap_completed_at, bootstrapped_by, promoted_user_id)" in up
    runtime_sql = read("scripts/create_runtime_role.sql")
    assert "GRANT SELECT, INSERT ON TABLE public.admin_audit_log" in runtime_sql
    assert "GRANT UPDATE (bootstrap_completed_at, bootstrapped_by, promoted_user_id)" in runtime_sql
    assert "GRANT UPDATE (user_role) ON TABLE public.users" in up
    assert "REVOKE INSERT (user_role)" in up
    assert "009_super_admin" in up


def test_down_migration_refuses_to_remove_a_live_super_admin_hierarchy():
    down = read("migrations/009_super_admin_down.sql")
    assert "WHERE user_role = 'super_admin'" in down
    assert "bootstrap_completed_at IS NOT NULL" in down
    assert "RAISE EXCEPTION" in down
    assert "REVOKE UPDATE (user_role)" in down
    assert "GRANT INSERT (user_role)" in down


def test_student_creation_path_cannot_assign_privileged_roles():
    source = read("auth/store.py")
    create_user = source.split("def create_user(", 1)[1].split("def list_users(", 1)[0]
    assert 'if role != "student"' in create_user
    assert "(username, email, password_hash, must_change_password)" in create_user
    assert "INSERT INTO users" in create_user
    assert "user_role" not in create_user.split("sql =", 1)[1].split('"""', 2)[1]
    script = read("scripts/create_user.py")
    assert 'choices=("student",)' in script
    assert "Super Admin workflow" in script
    runtime_sql = read("scripts/create_runtime_role.sql")
    assert "GRANT INSERT (username, email, password_hash, must_change_password)" in runtime_sql
    assert "GRANT UPDATE (username, email, password_hash, is_active, must_change_password, user_role)" in runtime_sql


def test_privileged_mutations_use_database_transactions_and_atomic_audit():
    source = read("auth/store.py")
    assert "def _transactional_connection(self)" in source
    assert "with self._transactional_connection() as connection" in source
    assert "def bootstrap_super_admin(" in source
    assert "def create_privileged_user(" in source
    assert "def update_privileged_account(" in source
    assert "self._insert_privileged_audit(" in source
    assert "def _require_super_admin_actor(" in source
    assert "SELECT COUNT(*) AS active_count FROM users WHERE user_role = 'super_admin' AND is_active = TRUE" in source
    assert "if actor_id == target_user_id" in source
    assert "if new_role not in {\"student\", \"admin\", \"super_admin\"}" in source
    assert "last active Super Admin" in source
    assert "UPDATE auth_sessions SET revoked_at" in source
    create = source.split("def create_privileged_user(", 1)[1].split("def update_privileged_account(", 1)[0]
    assert 'if guard.get("bootstrap_completed_at") is None' in create


def test_bootstrap_requires_existing_verified_active_admin_and_exact_confirmation():
    source = read("scripts/bootstrap_super_admin.py")
    assert "store.authenticate(identifier, password)" in source
    assert 'user.role != "admin"' in source
    assert 'user.is_active' in source
    assert 'user.must_change_password' in source
    assert '"BOOTSTRAP SUPER ADMIN"' in source
    assert "store.bootstrap_super_admin(user.user_id, password)" in source


def test_super_admin_console_has_server_side_guards_and_explicit_confirmations():
    callbacks = read("admin/super_admin_callbacks.py")
    dashboard = read("admin/super_admin_dashboard.py")
    assert "def _require_super_admin()" in callbacks
    assert "is_super_admin_role" in callbacks
    assert "CREATE PRIVILEGED ACCOUNT" in callbacks
    assert "APPLY PRIVILEGED CHANGE" in callbacks
    assert "auth_store.create_privileged_user" in callbacks
    assert "auth_store.update_privileged_account" in callbacks
    assert "list_privileged_audit" in dashboard
    assert 'url_base_pathname="/super-admin/"' in dashboard
    assert '"account_status": "Active" if item.get("is_active") else "Deactivated"' in callbacks
    assert "Select an account first." in callbacks


def test_existing_admin_callbacks_accept_super_admin_role():
    paths = [
        "admin/gcp_callbacks.py", "admin/layer_callbacks.py", "admin/collection_callbacks.py",
        "admin/config_callbacks.py", "admin/coverage_callbacks.py", "admin/coverage_assignment_callbacks.py",
        "admin/context_category_callbacks.py", "admin/users_callbacks.py",
    ]
    for path in paths:
        source = read(path)
        assert "is_admin_role" in source, path


def test_bootstrap_and_privileged_audit_share_a_single_database_transaction():
    source = read("auth/store.py")
    bootstrap = source.split("def bootstrap_super_admin(", 1)[1].split("def create_privileged_user(", 1)[0]
    create = source.split("def create_privileged_user(", 1)[1].split("def update_privileged_account(", 1)[0]
    update = source.split("def update_privileged_account(", 1)[1].split("def list_privileged_audit(", 1)[0]
    for method in (bootstrap, create, update):
        assert "with self._transactional_connection() as connection" in method
        assert "self._insert_privileged_audit(" in method

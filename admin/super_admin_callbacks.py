from __future__ import annotations

import json

from dash import Input, Output, State, html, no_update
from flask import abort
from flask_login import current_user

from auth.permissions import is_super_admin_role
from services.admin_user_management import generate_temporary_password


def _require_super_admin() -> int:
    if not current_user.is_authenticated or not is_super_admin_role(getattr(current_user, "role", None)):
        abort(403)
    return int(current_user.get_id())


def _account_rows(auth_store) -> list[dict]:
    accounts = auth_store.list_users(include_gcp_count=False)
    accounts.sort(key=lambda item: (str(item.get("user_role")), str(item.get("username", "")).casefold()))
    return [
        {**item, "account_status": "Active" if item.get("is_active") else "Deactivated"}
        for item in accounts
    ]


def _audit_rows(auth_store) -> list[dict]:
    rows = auth_store.list_privileged_audit(limit=150)
    for row in rows:
        details = row.get("details") or {}
        row["details_text"] = json.dumps(details, ensure_ascii=False, sort_keys=True) if isinstance(details, (dict, list)) else str(details)
    return rows


def register_super_admin_callbacks(app, auth_store) -> None:
    @app.callback(
        Output("super-admin-revision", "data"),
        Output("super-admin-create-status", "children"),
        Output("super-admin-one-time-credentials", "children"),
        Input("super-admin-create-account", "n_clicks"),
        State("super-admin-new-username", "value"),
        State("super-admin-new-email", "value"),
        State("super-admin-new-role", "value"),
        State("super-admin-create-confirmation", "value"),
        State("super-admin-revision", "data"),
        prevent_initial_call=True,
    )
    def create_privileged_account(n_clicks, username, email, role, confirmation, revision):
        if not n_clicks:
            return no_update, no_update, no_update
        actor_id = _require_super_admin()
        if confirmation != "CREATE PRIVILEGED ACCOUNT":
            return no_update, "Confirmation phrase did not match. No account was created.", no_update
        try:
            temporary_password = generate_temporary_password()
            new_id = auth_store.create_privileged_user(
                actor_id,
                username=username or "",
                email=email or "",
                password=temporary_password,
                role=role,
            )
            credential_panel = html.Div([
                html.Strong("Temporary password — shown once"),
                html.Div([html.Span("Username: "), html.Code((username or "").strip())]),
                html.Div([html.Span("Email: "), html.Code((email or "").strip().lower())]),
                html.Div([html.Span("Temporary password: "), html.Code(temporary_password)]),
                html.P("The account must change this password at first sign-in. Copy it now; it cannot be retrieved later.", style={"margin": "6px 0 0", "fontSize": "11px", "color": "#1e40af"}),
            ])
            return int(revision or 0) + 1, f"Created {role} account (ID {new_id}).", credential_panel
        except Exception as exc:
            return no_update, f"Account creation failed: {exc}", no_update

    @app.callback(
        Output("super-admin-edit-role", "value"),
        Output("super-admin-edit-active", "value"),
        Output("super-admin-selection-status", "children"),
        Input("super-admin-accounts-table", "selectedRows"),
        prevent_initial_call=True,
    )
    def select_privileged_account(selected_rows):
        _require_super_admin()
        rows = selected_rows or []
        if not rows:
            return "admin", "active", "Select an account to manage."
        selected = rows[0]
        if str(selected.get("user_id")) == str(current_user.get_id()):
            return selected.get("user_role", "super_admin"), "active" if selected.get("is_active") else "inactive", "Your own account is read-only here; self-demotion and self-deactivation are blocked."
        if selected.get("user_role") not in {"student", "admin", "super_admin"}:
            return "student", "active", "This account has an unsupported role and cannot be changed here."
        return selected.get("user_role"), "active" if selected.get("is_active") else "inactive", f"Selected {selected.get('user_role')} account · {selected.get('username')} (ID {selected.get('user_id')})."

    @app.callback(
        Output("super-admin-revision", "data", allow_duplicate=True),
        Output("super-admin-manage-status", "children"),
        Input("super-admin-apply-change", "n_clicks"),
        State("super-admin-accounts-table", "selectedRows"),
        State("super-admin-edit-role", "value"),
        State("super-admin-edit-active", "value"),
        State("super-admin-edit-confirmation", "value"),
        State("super-admin-revision", "data"),
        prevent_initial_call=True,
    )
    def update_privileged_account(n_clicks, selected_rows, new_role, active_value, confirmation, revision):
        if not n_clicks:
            return no_update, no_update
        actor_id = _require_super_admin()
        if confirmation != "APPLY PRIVILEGED CHANGE":
            return no_update, "Confirmation phrase did not match. No changes were made."
        rows = selected_rows or []
        if not rows:
            return no_update, "Select an account first."
        target_id = int(rows[0].get("user_id"))
        try:
            result = auth_store.update_privileged_account(
                actor_id,
                target_id,
                new_role=new_role,
                is_active=(active_value == "active"),
            )
            if not result.get("changed"):
                return no_update, "No changes were necessary."
            status = "Active" if result["is_active"] else "Deactivated"
            return int(revision or 0) + 1, f"Updated {result['username']}: role {result['user_role']}, account {status}. Existing sessions were revoked."
        except Exception as exc:
            return no_update, f"Account update failed: {exc}"

    @app.callback(
        Output("super-admin-accounts-table", "rowData"),
        Output("super-admin-audit-table", "rowData"),
        Input("super-admin-revision", "data"),
    )
    def refresh_super_admin_data(_revision):
        _require_super_admin()
        return _account_rows(auth_store), _audit_rows(auth_store)

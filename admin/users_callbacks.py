from __future__ import annotations

import logging

from dash import Input, Output, State, ctx, dcc, html, no_update
from flask import abort
from flask_login import current_user

from services.admin_user_management import (
    credentials_csv_bytes,
    generate_temporary_password,
    parse_student_roster,
)


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _audit(auth_store, action: str, target_id=None, details=None) -> None:
    try:
        auth_store.log_admin_action(int(current_user.get_id()), action, "user", target_id, details or {})
    except Exception:
        # User management must still be clear about the account operation;
        # failed audit writes remain visible in the application log.
        logging.getLogger(__name__).exception("Could not write admin user-management audit record")


def _credentials_panel(username: str, email: str, password: str):
    return html.Div([
        html.Strong("Temporary password — shown once"),
        html.Div([html.Span("Username: "), html.Code(username)]),
        html.Div([html.Span("Email: "), html.Code(email)]),
        html.Div([html.Span("Temporary password: "), html.Code(password)]),
        html.P("Copy this credential now or use the downloaded CSV. The password is stored only as a hash and cannot be retrieved later.", style={"margin": "6px 0 0", "fontSize": "11px", "color": "#1e40af"}),
    ])


def register_admin_users_callbacks(app, auth_store) -> None:
    @app.callback(
        Output("admin-user-roster-preview", "rowData"),
        Output("admin-user-roster-store", "data"),
        Output("admin-user-roster-status", "children"),
        Input("admin-user-roster-upload", "contents"),
        State("admin-user-roster-upload", "filename"),
        prevent_initial_call=True,
    )
    def preview_roster(contents, filename):
        _require_admin()
        if not contents:
            return [], [], "No CSV selected."
        try:
            rows = parse_student_roster(contents)
            existing = auth_store.list_users(include_gcp_count=False)
            usernames = {str(x["username"]).casefold() for x in existing}
            emails = {str(x["email"]).casefold() for x in existing}
            preview = []
            clean_rows = []
            for row in rows:
                errors = [x for x in str(row.get("error") or "").split("; ") if x]
                if row["username"].casefold() in usernames:
                    errors.append("username already exists")
                if row["email"].casefold() in emails:
                    errors.append("email already exists")
                view = {**row, "error": "; ".join(errors)}
                preview.append(view)
                clean_rows.append({"username": row["username"], "email": row["email"], "error": "; ".join(errors)})
            valid = sum(not row["error"] for row in clean_rows)
            label = f"{filename or 'Roster'}: {len(rows)} row(s), {valid} valid, {len(rows)-valid} requiring correction."
            return preview, clean_rows, label
        except Exception as exc:
            return [], [], f"Roster could not be read: {exc}"

    @app.callback(
        Output("admin-users-revision", "data"),
        Output("admin-user-create-status", "children"),
        Output("admin-user-manage-status", "children"),
        Output("admin-user-one-time-credentials", "children"),
        Output("admin-user-credentials-download", "data"),
        Output("admin-users-table", "selectedRows"),
        Input("admin-create-user", "n_clicks"),
        Input("admin-import-user-roster", "n_clicks"),
        Input("admin-update-user", "n_clicks"),
        Input("admin-reset-user-password", "n_clicks"),
        Input("admin-toggle-user-active", "n_clicks"),
        State("admin-new-user-username", "value"),
        State("admin-new-user-email", "value"),
        State("admin-user-roster-store", "data"),
        State("admin-users-table", "selectedRows"),
        State("admin-edit-user-username", "value"),
        State("admin-edit-user-email", "value"),
        State("admin-users-revision", "data"),
        prevent_initial_call=True,
    )
    def apply_user_action(
        create_clicks, import_clicks, update_clicks, reset_clicks, toggle_clicks,
        new_username, new_email, roster_rows, selected_rows,
        edit_username, edit_email, revision,
    ):
        del create_clicks, import_clicks, update_clicks, reset_clicks, toggle_clicks
        _require_admin()
        triggered = ctx.triggered_id
        revision = int(revision or 0)
        no_status = no_update
        try:
            if triggered == "admin-create-user":
                password = generate_temporary_password()
                user_id = auth_store.create_user(
                    username=new_username or "", email=new_email or "",
                    password=password, role="student", must_change_password=True,
                )
                _audit(auth_store, "student_created", user_id, {"username": new_username})
                creds = [{"username": new_username.strip(), "email": new_email.strip().lower(), "temporary_password": password, "must_change_password": "true"}]
                return revision + 1, f"Student account created (ID {user_id}).", no_status, _credentials_panel(new_username.strip(), new_email.strip().lower(), password), dcc.send_bytes(credentials_csv_bytes(creds), "student_temporary_credentials.csv"), []

            if triggered == "admin-import-user-roster":
                rows = roster_rows or []
                if not rows:
                    raise ValueError("Upload and preview a roster before importing it.")
                existing = auth_store.list_users(include_gcp_count=False)
                usernames = {str(x["username"]).casefold() for x in existing}
                emails = {str(x["email"]).casefold() for x in existing}
                credentials, errors = [], []
                for row in rows:
                    username = str(row.get("username") or "").strip()
                    email = str(row.get("email") or "").strip().lower()
                    row_errors = [x for x in str(row.get("error") or "").split("; ") if x]
                    if username.casefold() in usernames:
                        row_errors.append("username already exists")
                    if email.casefold() in emails:
                        row_errors.append("email already exists")
                    if row_errors:
                        errors.append(f"{username or '(blank)'}: {', '.join(dict.fromkeys(row_errors))}")
                        continue
                    password = generate_temporary_password()
                    try:
                        user_id = auth_store.create_user(username=username, email=email, password=password, role="student", must_change_password=True)
                    except Exception as exc:
                        # A concurrent import/admin action can create the same
                        # username/email after preview. Keep other rows moving.
                        errors.append(f"{username}: {exc}")
                        continue
                    _audit(auth_store, "student_created_from_roster", user_id, {"username": username})
                    credentials.append({"username": username, "email": email, "temporary_password": password, "must_change_password": "true"})
                    usernames.add(username.casefold())
                    emails.add(email.casefold())
                if not credentials:
                    raise ValueError("No accounts were created. " + ("; ".join(errors[:12]) if errors else "Check the roster."))
                message = f"Created {len(credentials)} student account(s)."
                if errors:
                    message += f" Skipped {len(errors)} invalid, duplicate or failed row(s). Review the preview and correct the CSV."
                download = dcc.send_bytes(credentials_csv_bytes(credentials), "student_roster_temporary_credentials.csv")
                details = html.Div([html.Strong("Temporary credentials generated"), html.P("Only successful accounts are included in the downloaded CSV. Passwords are not retrievable from the database.", style={"fontSize": "11px", "margin": "4px 0"})])
                return revision + 1, no_status, message + " A one-time credential CSV was downloaded.", details, download, []

            rows = selected_rows or []
            if not rows:
                raise ValueError("Select a student account in the table first.")
            selected = rows[0]
            if str(selected.get("user_role")) != "student":
                raise ValueError("Administrator accounts are read-only in this page.")
            user_id = int(selected["user_id"])

            if triggered == "admin-update-user":
                auth_store.update_student_profile(user_id, username=edit_username or "", email=edit_email or "")
                _audit(auth_store, "student_profile_updated", user_id, {"username": edit_username})
                return revision + 1, no_status, "Student profile updated.", html.Div(), no_update, []

            if triggered == "admin-reset-user-password":
                password = generate_temporary_password()
                auth_store.reset_student_password(user_id, password)
                _audit(auth_store, "student_password_reset", user_id, {})
                creds = [{"username": selected.get("username", ""), "email": selected.get("email", ""), "temporary_password": password, "must_change_password": "true"}]
                return revision + 1, no_status, "Password reset. All sessions for this student have been revoked.", _credentials_panel(selected.get("username", ""), selected.get("email", ""), password), dcc.send_bytes(credentials_csv_bytes(creds), "student_password_reset_credentials.csv"), []

            if triggered == "admin-toggle-user-active":
                new_active = not bool(selected.get("is_active"))
                auth_store.set_student_active(user_id, new_active)
                _audit(auth_store, "student_activated" if new_active else "student_deactivated", user_id, {})
                message = "Student account reactivated." if new_active else "Student account deactivated; all active sessions have been revoked. Existing GCPs are preserved."
                return revision + 1, no_status, message, html.Div(), no_update, []

            return revision, no_status, no_status, no_update, no_update, no_update
        except Exception as exc:
            target = "admin-user-create-status" if triggered == "admin-create-user" else "admin-user-manage-status"
            message = f"Action failed: {exc}"
            return revision, message if target == "admin-user-create-status" else no_status, message if target != "admin-user-create-status" else no_status, no_update, no_update, no_update

    @app.callback(
        Output("admin-users-table", "rowData"),
        Input("admin-users-revision", "data"),
    )
    def refresh_users(_revision):
        _require_admin()
        users = auth_store.list_users()
        return [{**u, "account_status": "Active" if u.get("is_active") else "Deactivated", "must_change_password": "Yes" if u.get("must_change_password") else "No"} for u in users]

    @app.callback(
        Output("admin-edit-user-username", "value"),
        Output("admin-edit-user-email", "value"),
        Output("admin-user-selection-status", "children"),
        Input("admin-users-table", "selectedRows"),
        prevent_initial_call=True,
    )
    def populate_selected_user(selected_rows):
        _require_admin()
        rows = selected_rows or []
        if not rows:
            return "", "", "No account selected."
        selected = rows[0]
        if selected.get("user_role") != "student":
            return selected.get("username", ""), selected.get("email", ""), "Administrator selected — read-only."
        return selected.get("username", ""), selected.get("email", ""), f"Selected student · {selected.get('gcp_count', 0)} GCP contribution(s)."

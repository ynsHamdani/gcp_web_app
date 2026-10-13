from __future__ import annotations

import secrets

from dash import Input, Output, State, ctx, no_update
from flask import abort
from flask_login import current_user


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _options(users: list[dict]) -> list[dict]:
    return [
        {"label": f"{user['username']} ({user['email']})" + (" [inactive]" if not user["is_active"] else ""), "value": str(user["user_id"])}
        for user in users
    ]


def _rows(users: list[dict]) -> list[dict]:
    return [
        {
            "user_id": user.get("user_id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("user_role"),
            "active": "yes" if user.get("is_active") else "no",
            "created_at": user.get("created_at", ""),
        }
        for user in users
    ]


def _temporary_password() -> str:
    return secrets.token_urlsafe(18)


def register_admin_user_callbacks(app, auth_store):
    """Register student creation, profile updates, password reset, and deactivation."""

    @app.callback(
        Output("admin-user-table", "rowData"),
        Output("admin-user-select", "options"),
        Output("admin-user-result", "children"),
        Output("admin-user-temp-password", "children"),
        Output("edit-student-username", "value"),
        Output("edit-student-email", "value"),
        Output("admin-toggle-student", "children"),
        Output("new-student-username", "value"),
        Output("new-student-email", "value"),
        Input("admin-create-student", "n_clicks"),
        Input("admin-user-select", "value"),
        Input("admin-save-student", "n_clicks"),
        Input("admin-reset-student-password", "n_clicks"),
        Input("admin-toggle-student", "n_clicks"),
        State("new-student-username", "value"),
        State("new-student-email", "value"),
        State("edit-student-username", "value"),
        State("edit-student-email", "value"),
        prevent_initial_call=True,
    )
    def manage_student_accounts(
        create_clicks,
        selected_user_id,
        save_clicks,
        reset_clicks,
        toggle_clicks,
        new_username,
        new_email,
        edit_username,
        edit_email,
    ):
        del create_clicks, save_clicks, reset_clicks, toggle_clicks
        _require_admin()
        triggered = ctx.triggered_id
        temporary_password = ""
        message = ""
        clear_create_fields = False

        try:
            if triggered == "admin-create-student":
                username = (new_username or "").strip()
                email = (new_email or "").strip()
                temporary_password = _temporary_password()
                auth_store.create_user(
                    username=username,
                    email=email,
                    password=temporary_password,
                    role="student",
                )
                message = f"Student account created for {username}. Copy the temporary password now."
                clear_create_fields = True

            elif triggered == "admin-user-select":
                # Populate the edit fields from the server-side user list below.
                pass

            elif triggered == "admin-save-student":
                if not selected_user_id:
                    raise ValueError("Select a student account first.")
                auth_store.update_student_profile(
                    int(selected_user_id),
                    username=edit_username,
                    email=edit_email,
                )
                message = "Student details updated."

            elif triggered == "admin-reset-student-password":
                if not selected_user_id:
                    raise ValueError("Select a student account first.")
                temporary_password = _temporary_password()
                auth_store.reset_student_password(int(selected_user_id), temporary_password)
                message = "Temporary password generated. Copy it now and share it securely."

            elif triggered == "admin-toggle-student":
                if not selected_user_id:
                    raise ValueError("Select a student account first.")
                users_before = auth_store.list_users(role="student")
                selected = next((u for u in users_before if str(u["user_id"]) == str(selected_user_id)), None)
                if selected is None:
                    raise ValueError("Student account not found.")
                new_active_state = not bool(selected["is_active"])
                auth_store.set_student_active(int(selected_user_id), new_active_state)
                message = "Student account reactivated." if new_active_state else "Student account deactivated. Existing GCP records are preserved."

        except Exception as exc:
            message = f"Operation failed: {exc}"
            temporary_password = ""

        users = auth_store.list_users(role="student")
        selected = next((u for u in users if str(u["user_id"]) == str(selected_user_id)), None)
        if triggered == "admin-user-select":
            edit_username_out = selected.get("username", "") if selected else ""
            edit_email_out = selected.get("email", "") if selected else ""
            toggle_label = "Reactivate student" if selected and not selected.get("is_active") else "Deactivate student"
        else:
            edit_username_out = no_update
            edit_email_out = no_update
            toggle_label = "Reactivate student" if selected and not selected.get("is_active") else "Deactivate student"

        return (
            _rows(users),
            _options(users),
            message,
            f"Temporary password: {temporary_password}" if temporary_password else "",
            edit_username_out,
            edit_email_out,
            toggle_label,
            "" if clear_create_fields else no_update,
            "" if clear_create_fields else no_update,
        )

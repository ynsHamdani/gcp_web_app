from __future__ import annotations

from pathlib import Path

from dash import Dash
from flask import has_request_context
from flask_login import current_user

from auth.permissions import is_admin_role, is_super_admin_role
from flask_wtf.csrf import generate_csrf

from admin.users_callbacks import register_admin_users_callbacks
from ui.admin_users_layout import create_admin_users_layout

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mount_admin_users_dashboard(*, server, auth_store):
    app = Dash(
        "gcp_admin_users_dashboard", server=server,
        url_base_pathname="/admin/users/",
        assets_folder=str(_PROJECT_ROOT / "assets"),
        title="User Management", suppress_callback_exceptions=False,
    )

    def serve_layout():
        is_admin = has_request_context() and current_user.is_authenticated and is_admin_role(getattr(current_user, "role", None))
        is_super_admin = has_request_context() and current_user.is_authenticated and is_super_admin_role(getattr(current_user, "role", None))
        if is_admin:
            users = auth_store.list_users()
            username = current_user.username
            csrf = generate_csrf()
        else:
            users, username, csrf = [], "Administrator", ""
        return create_admin_users_layout(
            users=users, admin_username=username, csrf_token=csrf,
            is_super_admin=is_super_admin,
        )

    app.layout = serve_layout
    register_admin_users_callbacks(app, auth_store)
    return app

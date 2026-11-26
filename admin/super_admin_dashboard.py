from __future__ import annotations

from pathlib import Path
import json

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from admin.super_admin_callbacks import register_super_admin_callbacks
from auth.permissions import is_super_admin_role
from ui.super_admin_layout import create_super_admin_layout

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mount_super_admin_dashboard(*, server, auth_store):
    app = Dash(
        "gcp_super_admin_dashboard", server=server,
        url_base_pathname="/super-admin/",
        assets_folder=str(_PROJECT_ROOT / "assets"),
        title="Super Admin Console", suppress_callback_exceptions=False,
    )

    def serve_layout():
        allowed = has_request_context() and current_user.is_authenticated and is_super_admin_role(getattr(current_user, "role", None))
        if allowed:
            accounts = auth_store.list_users(include_gcp_count=False)
            accounts.sort(key=lambda item: (str(item.get("user_role")), str(item.get("username", "")).casefold()))
            audit_rows = auth_store.list_privileged_audit(limit=150)
            username = current_user.username
            csrf = generate_csrf()
        else:
            accounts, audit_rows, username, csrf = [], [], "Super Administrator", ""
        for row in audit_rows:
            details = row.get("details") or {}
            row["details_text"] = (
                json.dumps(details, ensure_ascii=False, sort_keys=True)
                if isinstance(details, (dict, list)) else str(details)
            )
        return create_super_admin_layout(users=accounts, audit_rows=audit_rows, username=username, csrf_token=csrf)

    app.layout = serve_layout
    register_super_admin_callbacks(app, auth_store)
    return app

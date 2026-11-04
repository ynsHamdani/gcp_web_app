from __future__ import annotations

from pathlib import Path

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from admin.config_callbacks import register_admin_config_callbacks
from config import GCP_CRS
from ui.admin_config_layout import create_admin_config_layout

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mount_admin_config_dashboard(*, server, settings_store, auth_store):
    app = Dash(
        "gcp_admin_config_dashboard", server=server,
        url_base_pathname="/admin/config/",
        assets_folder=str(_PROJECT_ROOT / "assets"),
        title="Configuration", suppress_callback_exceptions=False,
    )

    def serve_layout():
        is_admin = has_request_context() and current_user.is_authenticated and getattr(current_user, "role", None) == "admin"
        if is_admin:
            settings = settings_store.get_settings()
            username = current_user.username
            csrf = generate_csrf()
        else:
            settings, username, csrf = {"raster_ttl_hours": 24, "max_upload_size_mb": 256}, "Administrator", ""
        return create_admin_config_layout(
            settings=settings,
            gcp_crs=GCP_CRS,
            admin_username=username,
            csrf_token=csrf,
            secure_cookie=bool(server.config.get("SESSION_COOKIE_SECURE")),
            debug_mode=bool(server.debug),
        )

    app.layout = serve_layout
    register_admin_config_callbacks(app, settings_store, auth_store, GCP_CRS)
    return app

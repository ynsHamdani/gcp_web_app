from __future__ import annotations

from pathlib import Path

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from admin.coverage_callbacks import register_coverage_callbacks
from config import GCP_CRS
from storage.coverage_store import CoverageStore
from ui.admin_coverage_layout import create_admin_coverage_layout

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mount_coverage_dashboard(*, server, auth_store):
    """Mount the dedicated, admin-protected Coverage & Statistics interface."""
    coverage_store = CoverageStore(auth_store.pool)
    server.extensions["gcp_coverage_store"] = coverage_store

    app = Dash(
        "gcp_admin_coverage_dashboard",
        server=server,
        url_base_pathname="/admin/coverage/",
        assets_folder=str(_PROJECT_ROOT / "assets"),
        title="Coverage & Statistics",
        suppress_callback_exceptions=False,
    )

    def serve_layout():
        is_admin = (
            has_request_context()
            and current_user.is_authenticated
            and getattr(current_user, "role", None) == "admin"
        )
        if is_admin:
            layers = coverage_store.list_layers()
            username = current_user.username
            csrf = generate_csrf()
        else:
            layers, username, csrf = [], "Administrator", ""
        return create_admin_coverage_layout(
            layers=layers,
            admin_username=username,
            csrf_token=csrf,
            target_srid=int(str(GCP_CRS).split(":")[-1]),
        )

    app.layout = serve_layout
    register_coverage_callbacks(app, coverage_store)
    return app

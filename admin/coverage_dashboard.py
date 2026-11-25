from __future__ import annotations

from pathlib import Path

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from admin.coverage_callbacks import register_coverage_callbacks
from config import DATA_DIR, GCP_CRS
from services.coverage_staging import CoverageStagingStore
from storage.coverage_store import CoverageStore
from ui.admin_coverage_layout import create_admin_coverage_layout

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def mount_coverage_dashboard(*, server, auth_store):
    """Mount the dedicated Coverage & Statistics application for administrators."""
    coverage_store = CoverageStore(auth_store.pool)
    staging_store = CoverageStagingStore(DATA_DIR / "coverage_staging")
    server.extensions["gcp_coverage_store"] = coverage_store
    server.extensions["gcp_coverage_staging_store"] = staging_store

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
        selectable = [item for item in layers if item.get("is_active") and not item.get("is_suppressed")]
        selected_layer_id = selectable[0]["coverage_layer_id"] if selectable else None
        map_bounds = coverage_store.get_layer_bounds(selected_layer_id) if selected_layer_id else None
        return create_admin_coverage_layout(
            layers=layers,
            admin_username=username,
            csrf_token=csrf,
            target_srid=int(str(GCP_CRS).split(":")[-1]),
            selected_layer_id=selected_layer_id,
            initial_map_bounds=map_bounds,
        )

    app.layout = serve_layout
    register_coverage_callbacks(app, coverage_store, staging_store)
    return app

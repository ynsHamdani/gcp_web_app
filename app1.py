from __future__ import annotations

import atexit

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from auth import init_auth
from auth.store import AuthStore
from admin.dashboard import mount_admin_dashboard
from callbacks.export import register_student_export_callbacks
from callbacks.gcp import register_gcp_callbacks
from callbacks.navigation import register_navigation_callbacks
from callbacks.opacity import register_opacity_callbacks
from callbacks.raster import (
    register_raster_callbacks,
    register_raster_routes,
)
from database.db import close_db_pool, get_db_pool
from maps.map_views import (
    create_historical_map,
    create_reference_map,
)
from models.gcp import gcp_table_row
from storage.gcp_store import PostgresGCPStore
from storage.layer_store import PostgresLayerStore
from ui.controls import create_app_layout
from config import SECRET_KEY, RASTER_SIGNING_KEY


# =========================================================
# APPLICATION
# =========================================================

app = Dash(
    __name__,
    title="Historical Map GCP Collection",
    suppress_callback_exceptions=True,
)


# =========================================================
# POSTGRESQL STORAGE
# =========================================================

# Authentication does not exist yet, so config.yaml supplies one development
# user ID. Later the authentication/session layer will provide the current
# user's ID without changing the storage interfaces.
db_pool = get_db_pool()
auth_store = AuthStore(db_pool)
init_auth(
    app.server,
    auth_store,
    secret_key=SECRET_KEY,
    raster_signing_key=RASTER_SIGNING_KEY,
)

gcp_store = PostgresGCPStore(db_pool)
reference_layer_store = PostgresLayerStore(db_pool)
historical_layer_store = PostgresLayerStore(db_pool)

# Initial rows are resolved per request in serve_layout(), after the
# authenticated user is known. Never cache one student's GCPs globally.
initial_gcp_records = []
initial_gcp_rows = []

atexit.register(close_db_pool)


# =========================================================
# MAPS + PAGE LAYOUT
# =========================================================

reference_map = create_reference_map()
historical_map = create_historical_map()

def serve_layout():
    # Dash may evaluate the layout once at startup without a request.
    # Only read Flask-Login/session state inside a request context.
    if has_request_context() and current_user.is_authenticated:
        auth_username = current_user.username
        auth_role = current_user.role
        csrf_token = generate_csrf()
    else:
        auth_username = None
        auth_role = None
        csrf_token = ""

    # Load personal GCPs at request time. Admins use the separate
    # administration interface, not the student GCP page.
    initial_gcp_records = []
    if (
        has_request_context()
        and current_user.is_authenticated
        and auth_role == "student"
    ):
        initial_gcp_records = gcp_store.list_for_student(
            int(current_user.get_id())
        )
    initial_gcp_rows = [
        gcp_table_row(record)
        for record in initial_gcp_records
    ]

    return create_app_layout(
        reference_map=reference_map,
        historical_map=historical_map,
        initial_records=initial_gcp_records,
        initial_rows=initial_gcp_rows,
        auth_username=auth_username,
        auth_role=auth_role,
        csrf_token=csrf_token,
    )


app.layout = serve_layout


# =========================================================
# ROUTES + CALLBACKS
# =========================================================

register_raster_routes(app)

register_raster_callbacks(app)

register_navigation_callbacks(app)
register_opacity_callbacks(app)
register_gcp_callbacks(app, gcp_store)

register_student_export_callbacks(app, gcp_store)

admin_dash_app = mount_admin_dashboard(
    server=app.server,
    gcp_store=gcp_store,
    layer_store=reference_layer_store,
    auth_store=auth_store,
)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)

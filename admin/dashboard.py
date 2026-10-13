from __future__ import annotations

from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf
from dash import Dash, html

from admin.gcp_callbacks import register_admin_gcp_callbacks
from admin.user_callbacks import register_admin_user_callbacks
from maps.map_views import create_historical_map, create_reference_map
from services.admin_layers import build_admin_layer_state, install_registry_on_map
from services.layer_availability import annotate_gcp_raster_availability
from ui.admin_layout import create_admin_layout


def _student_options(users: list[dict]) -> list[dict]:
    return [
        {"label": f"{user['username']} ({user['email']})", "value": str(user["user_id"])}
        for user in users
    ]


def mount_admin_dashboard(*, server, gcp_store, layer_store, auth_store):
    """Mount a second Dash app at /admin/ on the authenticated Flask server."""

    admin_app = Dash(
        "gcp_admin_dashboard",
        server=server,
        url_base_pathname="/admin/",
        title="GCP Administration",
        suppress_callback_exceptions=False,
    )

    def serve_admin_layout():
        # Dash can ask for a validation layout outside a Flask request.
        has_admin_session = (
            has_request_context()
            and current_user.is_authenticated
            and getattr(current_user, "role", None) == "admin"
        )

        if has_admin_session:
            records = gcp_store.list_for_admin()
            users = auth_store.list_users(role="student")
            layer_state = build_admin_layer_state(layer_store)
            csrf_token = generate_csrf()
        else:
            # Keep all callback component IDs present during Dash's startup
            # validation; Flask route guards deny unauthorized HTTP requests.
            records = []
            users = []
            layer_state = {
                "reference_registry": [],
                "historical_registry": [],
                "historical_options": [],
                "unavailable_layers": [],
            }
            csrf_token = ""

        reference_map = create_reference_map()
        historical_map = create_historical_map()
        install_registry_on_map(
            reference_map,
            layer_state["reference_registry"],
            "reference",
        )
        install_registry_on_map(
            historical_map,
            layer_state["historical_registry"],
            "historical",
        )
        return create_admin_layout(
            reference_map=reference_map,
            historical_map=historical_map,
            records=annotate_gcp_raster_availability(records),
            historical_options=layer_state["historical_options"],
            student_options=_student_options(users),
            users=users,
            unavailable_layers=layer_state["unavailable_layers"],
            csrf_token=csrf_token,
        )

    admin_app.layout = serve_admin_layout
    register_admin_gcp_callbacks(admin_app, gcp_store)
    register_admin_user_callbacks(admin_app, auth_store)
    return admin_app

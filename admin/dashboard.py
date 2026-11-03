from __future__ import annotations

from pathlib import Path

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from admin.gcp_callbacks import register_admin_gcp_callbacks
from maps.admin_gcp import install_admin_gcp_layer
from maps.map_views import create_historical_map, create_reference_map
from services.admin_layers import build_admin_layer_state, install_registry_on_map
from services.layer_availability import annotate_gcp_raster_availability
from ui.admin_layout import create_admin_layout


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _contributor_options(users: list[dict]) -> list[dict]:
    """Include all active and inactive students and administrators as owners."""

    options = []
    for user in users:
        role = str(user.get("user_role") or "user").strip().lower()
        role_label = "Admin" if role == "admin" else "Student"
        inactive = " · inactive" if not user.get("is_active", True) else ""
        username = str(user.get("username") or f"User {user.get('user_id')}")
        email = str(user.get("email") or "")
        suffix = f" · {email}" if email else ""
        options.append(
            {
                "label": f"{username} ({role_label}){suffix}{inactive}",
                "value": str(user["user_id"]),
            }
        )
    return options


def _default_available_layer(records: list[dict], registry: list[dict], field: str):
    """Choose one frequently referenced available layer for initial display."""

    available = {str(item.get("db_layer_id")) for item in registry}
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "")
        if value in available:
            counts[value] = counts.get(value, 0) + 1
    if not counts:
        return []
    best = max(counts, key=counts.get)
    return [best]


def mount_admin_dashboard(*, server, gcp_store, layer_store, auth_store):
    """Mount the protected Admin GCP Workspace at /admin/."""

    admin_app = Dash(
        "gcp_admin_dashboard",
        server=server,
        url_base_pathname="/admin/",
        assets_folder=str(_PROJECT_ROOT / "assets"),
        title="GCP Administration",
        suppress_callback_exceptions=False,
    )

    def serve_admin_layout():
        has_admin_session = (
            has_request_context()
            and current_user.is_authenticated
            and getattr(current_user, "role", None) == "admin"
        )

        if has_admin_session:
            records = annotate_gcp_raster_availability(gcp_store.list_for_admin())
            # Include admins as GCP contributors, not only student accounts.
            users = auth_store.list_users()
            layer_state = build_admin_layer_state(layer_store)
            csrf_token = generate_csrf()
            admin_username = current_user.username
        else:
            records = []
            users = []
            layer_state = {
                "reference_registry": [],
                "historical_registry": [],
                "historical_options": [],
                "unavailable_layers": [],
            }
            csrf_token = ""
            admin_username = "Administrator"

        reference_map = create_reference_map()
        historical_map = create_historical_map()

        reference_ids = _default_available_layer(
            records,
            layer_state["reference_registry"],
            "reference_layer_id",
        )
        historical_ids = _default_available_layer(
            records,
            layer_state["historical_registry"],
            "historical_layer_id",
        )

        install_registry_on_map(
            reference_map,
            layer_state["reference_registry"],
            "reference",
            reference_ids,
        )
        install_registry_on_map(
            historical_map,
            layer_state["historical_registry"],
            "historical",
            historical_ids,
        )
        install_admin_gcp_layer(reference_map, records, "reference")
        install_admin_gcp_layer(historical_map, records, "historical")

        return create_admin_layout(
            reference_map=reference_map,
            historical_map=historical_map,
            records=records,
            historical_options=layer_state["historical_options"],
            contributor_options=_contributor_options(users),
            layer_state=layer_state,
            unavailable_layers=layer_state["unavailable_layers"],
            csrf_token=csrf_token,
            admin_username=admin_username,
        )

    admin_app.layout = serve_admin_layout
    register_admin_gcp_callbacks(admin_app, gcp_store, layer_store)
    return admin_app

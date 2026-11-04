from __future__ import annotations

from pathlib import Path

from dash import Dash
from flask import has_request_context
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from admin.collection_callbacks import register_admin_collection_callbacks
from admin.config_dashboard import mount_admin_config_dashboard
from admin.gcp_callbacks import register_admin_gcp_callbacks
from admin.layer_callbacks import register_admin_layer_callbacks
from admin.users_dashboard import mount_admin_users_dashboard
from maps.admin_gcp import install_admin_gcp_layer
from maps.map_views import create_historical_map, create_reference_map
from services.admin_layers import build_admin_layer_state, install_registry_on_map
from services.layer_availability import annotate_gcp_raster_availability
from storage.settings_store import PostgresSettingsStore
from ui.admin_layout import create_admin_layout

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _contributor_options(users: list[dict]) -> list[dict]:
    options = []
    for user in users:
        role = str(user.get("user_role") or "user").strip().lower()
        role_label = "Admin" if role == "admin" else "Student"
        inactive = " · inactive" if not user.get("is_active", True) else ""
        email = str(user.get("email") or "")
        suffix = f" · {email}" if email else ""
        username = str(user.get("username") or "User " + str(user.get("user_id")))
        options.append({
            "label": f"{username} ({role_label}){suffix}{inactive}",
            "value": str(user["user_id"]),
        })
    return options


def _default_available_layer(records: list[dict], registry: list[dict], field: str) -> str | None:
    available = {str(item.get("db_layer_id")) for item in registry or []}
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "")
        if value in available:
            counts[value] = counts.get(value, 0) + 1
    return max(counts, key=counts.get) if counts else None


def _empty_layer_state() -> dict:
    return {
        "reference_registry": [], "historical_registry": [],
        "reference_options": [], "historical_options": [],
        "available_historical_options": [], "unavailable_layers": [],
        "basemap_reference_layer_id": None,
    }


def mount_admin_dashboard(*, server, gcp_store, layer_store, auth_store):
    """Mount GCP Workspace, User Management and Configuration as separate protected Dash pages."""
    settings_store = server.extensions.get("gcp_settings_store") or PostgresSettingsStore(auth_store.pool)
    server.extensions["gcp_settings_store"] = settings_store

    admin_app = Dash(
        "gcp_admin_dashboard", server=server, url_base_pathname="/admin/",
        assets_folder=str(_PROJECT_ROOT / "assets"), title="GCP Administration",
        suppress_callback_exceptions=False,
    )

    def serve_admin_layout():
        has_admin_session = has_request_context() and current_user.is_authenticated and getattr(current_user, "role", None) == "admin"
        if has_admin_session:
            records = annotate_gcp_raster_availability(gcp_store.list_for_admin())
            users = auth_store.list_users(include_gcp_count=False)
            layer_state = build_admin_layer_state(layer_store)
            csrf_token = generate_csrf()
            admin_username = current_user.username
        else:
            records, users, layer_state, csrf_token, admin_username = [], [], _empty_layer_state(), "", "Administrator"

        # Resolve the persisted provider for both maps on every page load.
        # create_basemap() falls back to OSM if CARTO is selected but the
        # local CARTO_API_KEY is missing, avoiding a blank basemap.
        basemap_provider = settings_store.get_value("basemap_provider", "carto")
        reference_map = create_reference_map(basemap_provider)
        historical_map = create_historical_map(basemap_provider)
        selected_reference_id = _default_available_layer(records, layer_state["reference_registry"], "reference_layer_id")
        selected_reference_id = selected_reference_id or layer_state.get("basemap_reference_layer_id")
        selected_historical_id = _default_available_layer(records, layer_state["historical_registry"], "historical_layer_id")
        if selected_historical_id is None and layer_state["historical_registry"]:
            selected_historical_id = str(layer_state["historical_registry"][0]["db_layer_id"])

        install_registry_on_map(reference_map, layer_state["reference_registry"], "reference", [selected_reference_id] if selected_reference_id else [])
        install_registry_on_map(historical_map, layer_state["historical_registry"], "historical", [selected_historical_id] if selected_historical_id else [])
        install_admin_gcp_layer(reference_map, records, "reference")
        install_admin_gcp_layer(historical_map, records, "historical")

        return create_admin_layout(
            reference_map=reference_map, historical_map=historical_map, records=records,
            historical_options=layer_state["historical_options"],
            contributor_options=_contributor_options(users), layer_state=layer_state,
            reference_layer_options=layer_state["reference_options"],
            historical_available_options=layer_state["available_historical_options"],
            selected_reference_layer_id=selected_reference_id,
            selected_historical_layer_id=selected_historical_id,
            unavailable_layers=layer_state["unavailable_layers"],
            csrf_token=csrf_token, admin_username=admin_username,
        )

    admin_app.layout = serve_admin_layout
    register_admin_gcp_callbacks(admin_app, gcp_store, layer_store)
    register_admin_layer_callbacks(admin_app, layer_store)
    register_admin_collection_callbacks(admin_app, gcp_store)

    # These are distinct Dash applications sharing the same protected Flask server.
    users_app = mount_admin_users_dashboard(server=server, auth_store=auth_store)
    config_app = mount_admin_config_dashboard(server=server, settings_store=settings_store, auth_store=auth_store)
    server.extensions["gcp_admin_apps"] = {"workspace": admin_app, "users": users_app, "config": config_app}
    return admin_app

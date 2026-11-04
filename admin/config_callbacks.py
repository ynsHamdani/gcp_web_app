from __future__ import annotations

from dash import Input, Output, State, no_update
from flask import abort, current_app
from flask_login import current_user

from services.runtime_settings import dash_request_max_content_length


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def register_admin_config_callbacks(app, settings_store, auth_store, gcp_crs: str) -> None:
    @app.callback(
        Output("admin-config-status", "children"),
        Input("admin-config-save", "n_clicks"),
        State("admin-config-raster-ttl", "value"),
        State("admin-config-max-upload-mb", "value"),
        prevent_initial_call=True,
    )
    def save_configuration(n_clicks, ttl_value, max_upload_value):
        if not n_clicks:
            return no_update
        _require_admin()
        try:
            if isinstance(ttl_value, bool) or int(ttl_value) != float(ttl_value):
                raise ValueError("Raster retention must be a whole number of hours.")
            if isinstance(max_upload_value, bool) or int(max_upload_value) != float(max_upload_value):
                raise ValueError("Maximum upload size must be a whole number of megabytes.")
            ttl = int(ttl_value)
            maximum = int(max_upload_value)
            # Validate both before mutating either setting.
            if not 1 <= ttl <= 8760:
                raise ValueError("Raster retention must be between 1 and 8760 hours.")
            if not 16 <= maximum <= 2048:
                raise ValueError("Maximum upload size must be between 16 and 2048 MB.")
            actor_id = int(current_user.get_id())
            # One multi-row upsert keeps both settings atomic on the AUTOCOMMIT adapter.
            settings_store.set_values(
                {"raster_ttl_hours": ttl, "max_upload_size_mb": maximum},
                actor_id,
            )
            # Flask enforces this request limit when Dash parses future POST
            # bodies. Decoded TIFF length is checked independently in maps.raster.
            current_app.config["MAX_CONTENT_LENGTH"] = dash_request_max_content_length(maximum)
            try:
                auth_store.log_admin_action(actor_id, "runtime_configuration_updated", "app_settings", None, {
                    "raster_ttl_hours": ttl,
                    "max_upload_size_mb": maximum,
                    "gcp_crs_read_only": gcp_crs,
                })
            except Exception:
                # Settings were committed atomically; an audit-write failure must
                # not be misreported as a failed configuration save.
                import logging
                logging.getLogger(__name__).exception("Could not write configuration audit record")
            return "Configuration saved. The upload limit applies to subsequent requests; the new raster TTL is used by subsequent cache cleanup operations."
        except Exception as exc:
            return f"Configuration was not saved: {exc}"

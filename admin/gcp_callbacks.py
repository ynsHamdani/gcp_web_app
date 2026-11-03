from __future__ import annotations

from dash import Input, Output, State, ctx, dcc, no_update
from flask import abort
from flask_login import current_user

from maps.admin_gcp import build_admin_gcp_geojson, build_admin_gcp_row
from services.gcp_export import build_gcp_csv
from services.layer_availability import annotate_gcp_raster_availability


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _optional_id(value, field_name: str) -> int | None:
    if value in (None, "", "all"):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name} filter value.") from exc
    if result <= 0:
        raise ValueError(f"Invalid {field_name} filter value.")
    return result


def _filtered_records(store, contributor_value, historical_value):
    _require_admin()
    contributor_id = _optional_id(contributor_value, "contributor")
    historical_layer_id = _optional_id(historical_value, "historical layer")
    return annotate_gcp_raster_availability(
        store.list_for_admin(
            student_id=contributor_id,
            historical_layer_id=historical_layer_id,
        )
    )


def _rows(records):
    return [build_admin_gcp_row(record) for record in records]


def _historical_options(layer_state: dict) -> list[dict]:
    return [
        {"label": "All historical layers", "value": "all"},
        *(layer_state.get("historical_options") or []),
    ]


def _raster_status(layer_state: dict, historical_value) -> str:
    """Return a short availability summary; names live in the expandable panel."""
    unavailable = list(layer_state.get("unavailable_layers") or [])
    if historical_value not in (None, "", "all"):
        selected = next(
            (item for item in layer_state.get("historical_options", [])
             if str(item.get("value")) == str(historical_value)),
            None,
        )
        if selected and "unavailable" in str(selected.get("label", "")).lower():
            if selected["label"] not in unavailable:
                unavailable.append(selected["label"])
    if unavailable:
        return (
            f"{len(unavailable)} registered raster(s) unavailable. "
            "Expand Layer availability in Add a GCP for details."
        )
    return "All registered raster files and map services are available."


def register_admin_gcp_callbacks(app, gcp_store, layer_store):
    """Register Step 1 filters/refresh/delete plus GCP-collection refresh."""

    @app.callback(
        Output("admin-gcp-table", "rowData"),
        Output("admin-gcp-records", "data"),
        Output("admin-reference-gcp-geojson", "data"),
        Output("admin-historical-gcp-geojson", "data"),
        Output("admin-gcp-status", "children"),
        Output("admin-raster-status", "children"),
        Output("admin-historical-filter", "options"),
        Input("admin-apply-filter", "n_clicks"),
        Input("admin-delete-gcp", "n_clicks"),
        Input("admin-gcp-collection-revision", "data"),
        Input("admin-layer-state", "data"),
        State("admin-contributor-filter", "value"),
        State("admin-historical-filter", "value"),
        State("admin-gcp-table", "selectedRows"),
        prevent_initial_call=True,
    )
    def update_admin_gcp_view(
        apply_clicks,
        delete_clicks,
        collection_revision,
        layer_state,
        contributor_value,
        historical_value,
        selected_rows,
    ):
        del apply_clicks, delete_clicks, collection_revision
        _require_admin()
        triggered = ctx.triggered_id
        status_prefix = ""
        layer_state = layer_state or {}

        if not layer_state:
            status_prefix = "Layer catalogue is not loaded yet. "

        if triggered == "admin-delete-gcp":
            selected_rows = selected_rows or []
            gcp_id = selected_rows[0].get("gcp_id") if selected_rows else None
            if not gcp_id:
                status_prefix = "Select a GCP record before deleting. "
            else:
                try:
                    gcp_store.delete(
                        gcp_id,
                        requester_id=int(current_user.get_id()),
                        requester_role="admin",
                    )
                    status_prefix = f"Deleted {gcp_id}. "
                except KeyError as exc:
                    status_prefix = f"{exc}. "
                except PermissionError as exc:
                    status_prefix = f"Deletion not permitted: {exc}. "
                except Exception as exc:
                    status_prefix = f"Deletion failed: {exc}. "

        try:
            records = _filtered_records(gcp_store, contributor_value, historical_value)
        except Exception as exc:
            return (
                no_update, no_update, no_update, no_update,
                f"Could not load filtered GCPs: {exc}",
                no_update, no_update,
            )

        if triggered == "admin-layer-state":
            status_prefix += "GCP records and raster availability refreshed. "
        elif triggered == "admin-apply-filter":
            status_prefix += "Filters applied. "
        elif triggered == "admin-gcp-collection-revision":
            status_prefix += "New administrator GCP saved; workspace refreshed. "

        return (
            _rows(records),
            records,
            build_admin_gcp_geojson(records, "reference"),
            build_admin_gcp_geojson(records, "historical"),
            f"{status_prefix}Showing {len(records)} GCP(s).",
            _raster_status(layer_state, historical_value),
            _historical_options(layer_state),
        )

    @app.callback(
        Output("admin-reference-gcp-geojson", "hideout"),
        Output("admin-historical-gcp-geojson", "hideout"),
        Output("admin-gcp-viewport-request", "data"),
        Input("admin-gcp-table", "selectedRows"),
        State("admin-gcp-records", "data"),
        prevent_initial_call=True,
    )
    def zoom_to_selected_gcp(selected_rows, records):
        _require_admin()
        selected_rows = selected_rows or []
        if not selected_rows:
            empty_hideout = {"selected_gcp_id": None}
            return empty_hideout, empty_hideout, no_update

        selected_id = str(selected_rows[0].get("gcp_id") or "")
        record = next(
            (item for item in (records or []) if str(item.get("gcp_id")) == selected_id),
            None,
        )
        if record is None:
            empty_hideout = {"selected_gcp_id": None}
            return empty_hideout, empty_hideout, no_update

        reference = record.get("reference") or {}
        historical = record.get("historical") or {}
        coordinates = (reference.get("lat"), reference.get("lon"), historical.get("lat"), historical.get("lon"))
        if any(value is None for value in coordinates):
            empty_hideout = {"selected_gcp_id": selected_id}
            return empty_hideout, empty_hideout, no_update

        center = [
            (float(reference["lat"]) + float(historical["lat"])) / 2.0,
            (float(reference["lon"]) + float(historical["lon"])) / 2.0,
        ]
        hideout = {"selected_gcp_id": selected_id}
        command = {"center": center, "zoom": 18, "request_id": f"gcp:{selected_id}"}
        return hideout, hideout, command

    # A single browser-side dispatcher applies all intentional map zooms.
    # Layer buttons and GCP-row selection publish separate requests, avoiding
    # duplicate Dash outputs and race conditions between the two zoom sources.
    app.clientside_callback(
        """
        function(layerCommand, gcpCommand) {
            const dash = window.dash_clientside;
            if (!dash || !dash.callback_context) return null;
            const triggered = dash.callback_context.triggered_id;
            const command = triggered === "admin-layer-viewport-request"
                ? layerCommand : gcpCommand;
            if (!command || !Array.isArray(command.center)) {
                return dash.no_update;
            }
            if (window.gcpMapSync && typeof window.gcpMapSync.setSynchronizedView === "function") {
                window.gcpMapSync.setSynchronizedView(command.center, command.zoom);
                return {request_id: command.request_id || null, applied: true};
            }
            return dash.no_update;
        }
        """,
        Output("admin-viewport-applied", "data"),
        Input("admin-layer-viewport-request", "data"),
        Input("admin-gcp-viewport-request", "data"),
    )

    @app.callback(
        Output("admin-gcp-table", "selectedRows"),
        Input("admin-gcp-table", "rowData"),
        prevent_initial_call=True,
    )
    def clear_selection_after_data_refresh(_row_data):
        return []

    @app.callback(
        Output("admin-gcp-download", "data"),
        Input("admin-export-gcps", "n_clicks"),
        State("admin-contributor-filter", "value"),
        State("admin-historical-filter", "value"),
        prevent_initial_call=True,
    )
    def export_admin_gcps(n_clicks, contributor_value, historical_value):
        if not n_clicks:
            return no_update
        records = _filtered_records(gcp_store, contributor_value, historical_value)
        return dcc.send_bytes(build_gcp_csv(records), "gcp_export.csv")

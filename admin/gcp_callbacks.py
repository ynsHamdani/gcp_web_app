from __future__ import annotations

from flask import abort
from flask_login import current_user
from dash import Input, Output, State, ctx, dcc, no_update

from maps.admin_gcp import build_admin_gcp_markers, build_admin_gcp_row
from services.gcp_export import build_gcp_csv
from services.layer_availability import annotate_gcp_raster_availability


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _filtered_records(store, student_value, layer_value):
    _require_admin()
    student_id = None if student_value in (None, "all", "") else int(student_value)
    layer_id = None if layer_value in (None, "all", "") else int(layer_value)
    return annotate_gcp_raster_availability(
        store.list_for_admin(student_id=student_id, historical_layer_id=layer_id)
    )


def _rows(records):
    return [build_admin_gcp_row(record) for record in records]


def register_admin_gcp_callbacks(app, gcp_store):
    """Register admin-owned filtering, deletion, and CSV callbacks."""

    @app.callback(
        Output("admin-gcp-table", "rowData"),
        Output("admin-gcp-records", "data"),
        Output("reference-gcp-layer", "children"),
        Output("historical-gcp-layer", "children"),
        Output("admin-gcp-status", "children"),
        Input("admin-apply-filter", "n_clicks"),
        Input("admin-refresh", "n_clicks"),
        Input("admin-delete-gcp", "n_clicks"),
        State("admin-student-filter", "value"),
        State("admin-historical-filter", "value"),
        State("admin-gcp-table", "selectedRows"),
        prevent_initial_call=True,
    )
    def update_admin_gcp_view(apply_clicks, refresh_clicks, delete_clicks, student_value, layer_value, selected_rows):
        del apply_clicks, refresh_clicks, delete_clicks
        _require_admin()
        triggered = ctx.triggered_id
        status_prefix = ""

        if triggered == "admin-delete-gcp":
            selected_rows = selected_rows or []
            if not selected_rows or not selected_rows[0].get("gcp_id"):
                current = _filtered_records(gcp_store, student_value, layer_value)
                return _rows(current), current, build_admin_gcp_markers(current, "reference"), build_admin_gcp_markers(current, "historical"), "Select a GCP in the table before deleting."
            gcp_id = selected_rows[0]["gcp_id"]
            try:
                gcp_store.delete(
                    gcp_id,
                    requester_id=int(current_user.get_id()),
                    requester_role="admin",
                )
                status_prefix = f"Deleted {gcp_id}. "
            except KeyError as exc:
                status_prefix = f"{exc} "
            except Exception as exc:
                current = _filtered_records(gcp_store, student_value, layer_value)
                return _rows(current), current, build_admin_gcp_markers(current, "reference"), build_admin_gcp_markers(current, "historical"), f"Deletion failed: {exc}"

        records = _filtered_records(gcp_store, student_value, layer_value)
        return (
            _rows(records),
            records,
            build_admin_gcp_markers(records, "reference"),
            build_admin_gcp_markers(records, "historical"),
            f"{status_prefix}Showing {len(records)} GCP(s).",
        )

    @app.callback(
        Output("admin-gcp-download", "data"),
        Input("admin-export-gcps", "n_clicks"),
        State("admin-student-filter", "value"),
        State("admin-historical-filter", "value"),
        prevent_initial_call=True,
    )
    def export_admin_gcps(n_clicks, student_value, layer_value):
        if not n_clicks:
            return no_update
        records = _filtered_records(gcp_store, student_value, layer_value)
        return dcc.send_bytes(build_gcp_csv(records), "gcp_export.csv")

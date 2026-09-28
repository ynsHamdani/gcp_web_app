from __future__ import annotations

"""Dash interaction workflow for Ground Control Points.

This module handles GCP interaction/orchestration only.

- Leaflet provides map positions in WGS84 (lat/lon).
- The domain model converts those positions to the project CRS (EPSG:25832).
- Persistence is handled by the injected GCPStore.

The callback therefore remains independent of JSON/PostgreSQL storage.
"""

from dash import Input, Output, State, ctx, no_update

from config import GCP_CRS, GCP_STUDENT_ID
from maps.gcp import build_gcp_layer_children
from models.gcp import (
    build_gcp_record,
    displacement_m,
    gcp_table_row,
    leaflet_to_gcp_position,
    normalize_position,
)
from storage.gcp_store import GCPStore


def _format_pending_status(pending: dict) -> str:
    """Build a compact status line using projected EPSG:25832 coordinates."""

    reference = leaflet_to_gcp_position(
        [pending["reference"]["lat"], pending["reference"]["lon"]]
    )
    historical = leaflet_to_gcp_position(
        [pending["historical"]["lat"], pending["historical"]["lon"]]
    )

    offset = displacement_m(reference, historical)

    return (
        "Pending GCP — "
        f"Reference ({GCP_CRS}): {reference['x']:.3f}, {reference['y']:.3f} | "
        f"Historical: {historical['x']:.3f}, {historical['y']:.3f} | "
        f"Offset: {offset:.2f} m"
    )


def _pending_position(position) -> dict[str, float]:
    """Normalize Leaflet coordinates for the application's map state.

    Leaflet/Dash can provide coordinates in either of these forms:

        [lat, lon]
        {"lat": lat, "lng": lon}

    The latter is what ``clickData["latlng"]`` normally provides.
    Internally we keep the application's pending-point representation as:

        {"lat": ..., "lon": ...}
    """

    if isinstance(position, dict):
        lat = position.get("lat")
        lon = position.get("lon", position.get("lng"))

        if lat is None or lon is None:
            raise ValueError("Invalid Leaflet coordinate dictionary.")

        position = [lat, lon]

    return normalize_position(position)


def _extract_click_position(click_data):
    """Extract a map position from Dash Leaflet clickData."""

    if not click_data:
        return None

    # Standard Dash Leaflet clickData form:
    # {"latlng": {"lat": ..., "lng": ...}, ...}
    latlng = click_data.get("latlng")
    if latlng:
        return latlng

    # Be tolerant of a direct coordinate payload.
    if "lat" in click_data and ("lng" in click_data or "lon" in click_data):
        return click_data

    return None


def _extract_drag_position(drag_event):
    """Extract a historical-marker position from the drag event payload."""

    if not drag_event:
        return None

    position = drag_event.get("position")
    if position:
        return position

    # Be tolerant if the browser-side bridge returns lat/lng directly.
    if "lat" in drag_event and ("lng" in drag_event or "lon" in drag_event):
        return drag_event

    return None


def register_gcp_callbacks(app, store: GCPStore):
    """Register all GCP interaction callbacks."""

    # -----------------------------------------------------
    # GCP COLLECTION MODE + ACTIVE GCP WORKFLOW
    # -----------------------------------------------------

    @app.callback(
        Output("gcp-pending", "data"),
        Output("gcp-records", "data"),
        Output("gcp-status", "children"),
        Output("confirm-gcp-button", "disabled"),
        Output("cancel-gcp-button", "disabled"),
        Output("gcp-drag-event", "clear_data"),
        Output("gcp-collection-active", "data"),
        Output("add-gcp-button", "children"),
        Input("add-gcp-button", "n_clicks"),
        Input("reference-map", "clickData"),
        Input("gcp-drag-event", "data"),
        Input("confirm-gcp-button", "n_clicks"),
        Input("cancel-gcp-button", "n_clicks"),
        State("gcp-pending", "data"),
        State("gcp-records", "data"),
        State("gcp-collection-active", "data"),
        State("reference-layer-zoom-select", "value"),
        State("historical-layer-zoom-select", "value"),
        prevent_initial_call=True,
    )
    def manage_gcp_workflow(
        add_clicks,
        reference_click,
        drag_event,
        confirm_clicks,
        cancel_clicks,
        pending,
        records,
        collection_active,
        reference_layer_id,
        historical_layer_id,
    ):
        del add_clicks, confirm_clicks, cancel_clicks

        records = records or []
        collection_active = bool(collection_active)
        triggered = ctx.triggered_id

        # -----------------------------
        # Toggle GCP collection mode
        # -----------------------------
        if triggered == "add-gcp-button":
            collection_active = not collection_active

            if collection_active:
                if pending:
                    status = _format_pending_status(pending)
                else:
                    status = (
                        "GCP collection active — "
                        "click a point on the reference map."
                    )

                return (
                    no_update,
                    no_update,
                    status,
                    not bool(pending),
                    not bool(pending),
                    True,
                    True,
                    "Stop GCP",
                )

            if pending:
                status = (
                    _format_pending_status(pending)
                    + " | Collection paused."
                )
            else:
                status = "GCP collection inactive — click Add GCP to start."

            return (
                no_update,
                no_update,
                status,
                not bool(pending),
                not bool(pending),
                True,
                False,
                "Add GCP",
            )

        # -----------------------------
        # Click reference map
        # -----------------------------
        if triggered == "reference-map":
            if not collection_active:
                return (
                    no_update,
                    no_update,
                    (
                        "GCP collection inactive — "
                        "click Add GCP before selecting a point."
                    ),
                    not bool(pending),
                    not bool(pending),
                    True,
                    collection_active,
                    "Add GCP",
                )

            if pending:
                return (
                    no_update,
                    no_update,
                    "A GCP is already pending. Confirm or cancel it first.",
                    False,
                    False,
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            click_position = _extract_click_position(reference_click)

            if click_position is None:
                return (
                    no_update,
                    no_update,
                    "Could not read the clicked map position.",
                    True,
                    True,
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            reference = _pending_position(click_position)

            pending = {
                "reference": reference,
                # Start the historical point at exactly the same geographic
                # position. The student then drags it to the matching feature.
                "historical": dict(reference),
                "reference_layer_id": reference_layer_id,
                "historical_layer_id": historical_layer_id,
            }

            return (
                pending,
                records,
                _format_pending_status(pending),
                False,
                False,
                True,
                collection_active,
                "Stop GCP",
            )

        # -----------------------------
        # Drag historical marker
        # -----------------------------
        if triggered == "gcp-drag-event":
            drag_position = _extract_drag_position(drag_event)

            if not pending or drag_position is None:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            pending = dict(pending)
            pending["historical"] = _pending_position(drag_position)

            return (
                pending,
                records,
                _format_pending_status(pending),
                False,
                False,
                True,
                collection_active,
                "Stop GCP" if collection_active else "Add GCP",
            )

        # -----------------------------
        # Confirm current GCP
        # -----------------------------
        if triggered == "confirm-gcp-button":
            if not pending:
                return (
                    no_update,
                    no_update,
                    "No pending GCP to confirm.",
                    True,
                    True,
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            record = build_gcp_record(
                reference_position=[
                    pending["reference"]["lat"],
                    pending["reference"]["lon"],
                ],
                historical_position=[
                    pending["historical"]["lat"],
                    pending["historical"]["lon"],
                ],
                student=GCP_STUDENT_ID,
                reference_layer_id=pending.get("reference_layer_id"),
                historical_layer_id=pending.get("historical_layer_id"),
            )

            saved = store.create(record)
            records = store.list()

            if collection_active:
                status = (
                    f"Confirmed {saved['gcp_id']} — "
                    f"offset: {saved['offset_m']:.2f} m | "
                    "Ready for next point."
                )
            else:
                status = (
                    f"Confirmed {saved['gcp_id']} — "
                    f"offset: {saved['offset_m']:.2f} m"
                )

            return (
                None,
                records,
                status,
                True,
                True,
                True,
                collection_active,
                "Stop GCP" if collection_active else "Add GCP",
            )

        # -----------------------------
        # Cancel current GCP
        # -----------------------------
        if triggered == "cancel-gcp-button":
            status = (
                "GCP cancelled — click a point on the reference map."
                if collection_active
                else "GCP cancelled — GCP collection inactive."
            )

            return (
                None,
                records,
                status,
                True,
                True,
                True,
                collection_active,
                "Stop GCP" if collection_active else "Add GCP",
            )

        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            True,
            collection_active,
            "Stop GCP" if collection_active else "Add GCP",
        )

    # -----------------------------------------------------
    # RENDER MARKERS + TABLE
    # -----------------------------------------------------

    @app.callback(
        Output("reference-gcp-layer", "children"),
        Output("historical-gcp-layer", "children"),
        Output("gcp-table", "rowData"),
        Input("gcp-records", "data"),
        Input("gcp-pending", "data"),
        Input("gcp-selected-id", "data"),
    )
    def render_gcp_state(records, pending, selected_gcp_id):
        records = records or []

        reference_children = build_gcp_layer_children(
            records,
            pending,
            selected_gcp_id,
            "reference",
        )

        historical_children = build_gcp_layer_children(
            records,
            pending,
            selected_gcp_id,
            "historical",
        )

        rows = [gcp_table_row(record) for record in records]

        return reference_children, historical_children, rows

    # -----------------------------------------------------
    # TABLE ROW SELECTION -> VISUAL HIGHLIGHT
    # -----------------------------------------------------

    @app.callback(
        Output("gcp-selected-id", "data"),
        Input("gcp-table", "selectedRows"),
        prevent_initial_call=True,
    )
    def select_gcp(rows):
        if not rows:
            return None

        return rows[0].get("gcp_id")

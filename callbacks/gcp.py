from __future__ import annotations

"""Dash interaction workflow for Ground Control Points.

Persistence is injected through GCPStore. The callback keeps the UI/browser
workflow independent of JSON/PostgreSQL implementation details.
"""

from pathlib import Path

from dash import Input, Output, State, ctx, no_update

from config import GCP_CRS, GCP_STUDENT_ID
from maps.gcp import build_gcp_layer_children
from maps.raster import geographic_to_pixel_line
from models.gcp import (
    build_gcp_record,
    displacement_m,
    gcp_table_row,
    leaflet_to_gcp_position,
    normalize_position,
)
from storage.gcp_store import GCPStore


# =========================================================
# HELPERS
# =========================================================


def _format_pending_status(pending: dict, message: str | None = None) -> str:
    """Build the pending-GCP status line."""

    reference = leaflet_to_gcp_position(pending["reference"])
    historical = leaflet_to_gcp_position(pending["historical"])
    offset = displacement_m(reference, historical)

    status = (
        "Pending GCP — "
        f"Reference ({GCP_CRS}): {reference['x']:.3f}, {reference['y']:.3f} | "
        f"Historical: {historical['x']:.3f}, {historical['y']:.3f} | "
        f"Offset: {offset:.2f} m"
    )

    if message:
        status += f" | {message}"

    return status


def _pending_position(position) -> dict[str, float]:
    """Normalize Leaflet coordinates for internal pending-point state."""

    return normalize_position(position)


def _extract_click_position(click_data):
    """Extract a map position from Dash Leaflet clickData."""

    if not click_data:
        return None

    latlng = click_data.get("latlng")
    if latlng:
        return latlng

    if "lat" in click_data and (
        "lng" in click_data or "lon" in click_data
    ):
        return click_data

    return None


def _extract_drag_position(drag_event):
    """Extract a historical-marker position from the browser drag bridge."""

    if not drag_event:
        return None

    position = drag_event.get("position")
    if position:
        return position

    if "lat" in drag_event and (
        "lng" in drag_event or "lon" in drag_event
    ):
        return drag_event

    return None


def _find_layer(layer_registry, layer_id):
    """Find one active raster-registry entry by ID."""

    if not layer_id:
        return None

    return next(
        (
            item
            for item in (layer_registry or [])
            if item.get("id") == layer_id
        ),
        None,
    )


def _historical_pixel_line(historical_position, historical_layer):
    """Return pixel/line for a historical-map position, or an error."""

    if not historical_layer:
        return None, "No historical raster is selected."

    cog_path = historical_layer.get("cog_path")
    if not cog_path:
        return None, "The selected historical raster has no COG path."

    position = normalize_position(historical_position)

    try:
        pixel_line = geographic_to_pixel_line(
            Path(cog_path),
            position["lon"],
            position["lat"],
        )
    except (ValueError, OSError) as exc:
        return None, str(exc)

    return pixel_line, None


def _find_gcp(records, gcp_id):
    """Find a GCP record by ID."""

    if not gcp_id:
        return None

    return next(
        (
            record
            for record in (records or [])
            if record.get("gcp_id") == gcp_id
        ),
        None,
    )


def register_gcp_callbacks(app, store: GCPStore):
    """Register all GCP interaction callbacks."""

    # =====================================================
    # GCP COLLECTION + ACTIVE GCP WORKFLOW
    # =====================================================

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
        Input("delete-gcp-button", "n_clicks"),
        State("gcp-pending", "data"),
        State("gcp-records", "data"),
        State("gcp-selected-id", "data"),
        State("gcp-collection-active", "data"),
        State("reference-layer-zoom-select", "value"),
        State("historical-layer-zoom-select", "value"),
        State("reference-layer-registry", "data"),
        State("historical-layer-registry", "data"),
        prevent_initial_call=True,
    )
    def manage_gcp_workflow(
        add_clicks,
        reference_click,
        drag_event,
        confirm_clicks,
        cancel_clicks,
        delete_clicks,
        pending,
        records,
        selected_gcp_id,
        collection_active,
        reference_layer_id,
        historical_layer_id,
        reference_layer_registry,
        historical_layer_registry,
    ):
        del add_clicks, confirm_clicks, cancel_clicks, delete_clicks

        records = records or []
        collection_active = bool(collection_active)
        triggered = ctx.triggered_id

        # =================================================
        # DELETE CONFIRMED GCP
        # =================================================

        if triggered == "delete-gcp-button":
            if not selected_gcp_id:
                return (
                    no_update,
                    no_update,
                    "Select a GCP in the table before deleting.",
                    not bool(pending),
                    not bool(pending),
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            try:
                store.delete(selected_gcp_id)
            except KeyError as exc:
                return (
                    no_update,
                    no_update,
                    str(exc),
                    not bool(pending),
                    not bool(pending),
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            records = store.list()

            return (
                pending,
                records,
                f"Deleted {selected_gcp_id}.",
                not bool(pending),
                not bool(pending),
                True,
                collection_active,
                "Stop GCP" if collection_active else "Add GCP",
            )

        historical_layer = _find_layer(
            historical_layer_registry,
            historical_layer_id,
        )

        # =================================================
        # TOGGLE GCP COLLECTION MODE
        # =================================================

        if triggered == "add-gcp-button":
            if not collection_active:
                if not historical_layer:
                    return (
                        no_update,
                        no_update,
                        "Upload and select a historical raster before adding GCPs.",
                        True,
                        True,
                        True,
                        False,
                        "Add GCP",
                    )

                return (
                    no_update,
                    no_update,
                    "GCP collection active — click a point on the reference map.",
                    not bool(pending),
                    not bool(pending),
                    True,
                    True,
                    "Stop GCP",
                )

            status = (
                _format_pending_status(pending, "Collection paused.")
                if pending
                else "GCP collection inactive."
            )

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

        # =================================================
        # CLICK REFERENCE MAP
        # =================================================

        if triggered == "reference-map":
            if not collection_active:
                return (
                    no_update,
                    no_update,
                    "GCP collection inactive — click Add GCP before selecting a point.",
                    not bool(pending),
                    not bool(pending),
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            if not historical_layer:
                return (
                    no_update,
                    no_update,
                    "Upload and select a historical raster before adding GCPs.",
                    True,
                    True,
                    True,
                    False,
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
                    "Stop GCP",
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
                    "Stop GCP",
                )

            reference = _pending_position(click_position)
            historical = dict(reference)

            pending = {
                "reference": reference,
                "historical": historical,
                "reference_layer_id": reference_layer_id,
                "historical_layer_id": historical_layer_id,
            }

            # Initially place the historical marker at the same geographic
            # location. It may lie outside the raster because the scan is not
            # yet correctly aligned.
            pixel_line, error = _historical_pixel_line(
                historical,
                historical_layer,
            )

            if pixel_line is not None:
                pending["historical_pixel"] = pixel_line["pixel"]
                pending["historical_line"] = pixel_line["line"]
                confirm_disabled = False
                message = "Drag the historical point to the matching feature."
            else:
                confirm_disabled = True
                message = (
                    "Historical point is outside the raster — "
                    "drag it inside the historical map."
                )

            return (
                pending,
                records,
                _format_pending_status(pending, message),
                confirm_disabled,
                False,
                True,
                collection_active,
                "Stop GCP",
            )

        # =================================================
        # DRAG HISTORICAL MARKER
        # =================================================

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

            # Re-resolve the exact historical layer used by this pending GCP.
            historical_layer = _find_layer(
                historical_layer_registry,
                pending.get("historical_layer_id"),
            )

            pending = dict(pending)
            pending["historical"] = _pending_position(drag_position)

            pixel_line, error = _historical_pixel_line(
                pending["historical"],
                historical_layer,
            )

            if pixel_line is None:
                pending.pop("historical_pixel", None)
                pending.pop("historical_line", None)

                return (
                    pending,
                    records,
                    _format_pending_status(
                        pending,
                        "Historical point is outside the raster — move it inside to confirm.",
                    ),
                    True,
                    False,
                    True,
                    collection_active,
                    "Stop GCP",
                )

            pending["historical_pixel"] = pixel_line["pixel"]
            pending["historical_line"] = pixel_line["line"]

            return (
                pending,
                records,
                _format_pending_status(
                    pending,
                    (
                        f"Historical pixel/line: "
                        f"{pixel_line['pixel']:.3f}, "
                        f"{pixel_line['line']:.3f}"
                    ),
                ),
                False,
                False,
                True,
                collection_active,
                "Stop GCP",
            )

        # =================================================
        # CONFIRM CURRENT GCP
        # =================================================

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

            historical_layer = _find_layer(
                historical_layer_registry,
                pending.get("historical_layer_id") or historical_layer_id,
            )

            if not historical_layer:
                return (
                    no_update,
                    no_update,
                    "The selected historical raster is no longer available.",
                    True,
                    False,
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            pixel_line, error = _historical_pixel_line(
                pending["historical"],
                historical_layer,
            )

            if pixel_line is None:
                return (
                    no_update,
                    no_update,
                    f"Cannot confirm GCP: {error}",
                    True,
                    False,
                    True,
                    collection_active,
                    "Stop GCP" if collection_active else "Add GCP",
                )

            record = build_gcp_record(
                reference_position=pending["reference"],
                historical_position=pending["historical"],
                historical_pixel=pixel_line["pixel"],
                historical_line=pixel_line["line"],
                student_id=GCP_STUDENT_ID,
                reference_layer_id=pending.get("reference_layer_id"),
                historical_layer_id=pending.get("historical_layer_id"),
            )

            saved = store.create(record)
            records = store.list()

            status = (
                f"Confirmed {saved['gcp_id']} — "
                f"pixel/line: "
                f"{saved['historical']['pixel']:.3f}, "
                f"{saved['historical']['line']:.3f}"
            )

            if collection_active:
                status += " | Ready for next point."

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

        # =================================================
        # CANCEL CURRENT GCP
        # =================================================

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

    # =====================================================
    # RENDER MARKERS + TABLE
    # =====================================================

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

    # =====================================================
    # TABLE ROW SELECTION -> HIGHLIGHT + DELETE ENABLE
    # =====================================================

    @app.callback(
        Output("gcp-selected-id", "data"),
        Output("delete-gcp-button", "disabled"),
        Input("gcp-table", "selectedRows"),
        Input("gcp-records", "data"),
        prevent_initial_call=True,
    )
    def select_gcp(rows, records):
        rows = rows or []
        records = records or []

        selected_id = None
        if rows:
            candidate = rows[0].get("gcp_id")
            if any(
                record.get("gcp_id") == candidate
                for record in records
            ):
                selected_id = candidate

        return selected_id, selected_id is None

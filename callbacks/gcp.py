from __future__ import annotations

"""Dash interaction workflow for Ground Control Points.

Important identity rule:
    - layer registry ``id`` remains the SHA-256 identity used by the UI.
    - ``db_layer_id`` is the PostgreSQL layers.layer_id used by gcps FKs.

Reference source:
    - uploaded reference raster -> its PostgreSQL layer_id
    - no uploaded reference raster -> OpenStreetMap basemap layer_id

Historical GCP:
    - Leaflet lat/lon is used for map interaction.
    - historical raster pixel/line are calculated from the actual COG.
"""

from pathlib import Path

import rasterio
from dash import Input, Output, State, ctx, no_update

from config import GCP_CRS, GCP_STUDENT_ID
from database.db import get_db_pool
from maps.gcp import build_gcp_layer_children
from models.gcp import (
    build_gcp_record,
    displacement_m,
    gcp_table_row,
    leaflet_to_gcp_position,
    normalize_position,
)
from storage.gcp_store import GCPStore
from storage.layer_store import PostgresLayerStore


_LAYER_STORE = PostgresLayerStore(get_db_pool())


def _format_pending_status(pending: dict) -> str:
    """Build a compact status line using projected EPSG:25832 coordinates."""

    reference = leaflet_to_gcp_position(
        [
            pending["reference"]["lat"],
            pending["reference"]["lon"],
        ]
    )

    historical = leaflet_to_gcp_position(
        [
            pending["historical"]["lat"],
            pending["historical"]["lon"],
        ]
    )

    offset = displacement_m(reference, historical)

    return (
        "Pending GCP — "
        f"Reference ({GCP_CRS}): "
        f"{reference['x']:.3f}, {reference['y']:.3f} | "
        f"Historical: "
        f"{historical['x']:.3f}, {historical['y']:.3f} | "
        f"Offset: {offset:.2f} m"
    )


def _pending_position(position) -> dict[str, float]:
    """Normalize a Leaflet click/drag position."""

    if isinstance(position, dict):
        lat = position.get("lat")
        lon = position.get("lon", position.get("lng"))

        if lat is None or lon is None:
            raise ValueError(
                "Invalid Leaflet coordinate dictionary."
            )

        position = [lat, lon]

    return normalize_position(position)


def _extract_click_position(click_data):
    """Extract coordinates from Dash Leaflet clickData."""

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
    """Extract coordinates from the browser drag bridge."""

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


def _find_registry_entry(
    registry: list[dict] | None,
    ui_layer_id,
) -> dict | None:
    """Find a layer-registry entry by its SHA/UI identity."""

    if not ui_layer_id:
        return None

    return next(
        (
            item
            for item in (registry or [])
            if item.get("id") == ui_layer_id
        ),
        None,
    )


def _get_db_layer_id(
    registry: list[dict] | None,
    ui_layer_id,
    *,
    layer_type: str,
) -> str | None:
    """Resolve a UI layer identity to its PostgreSQL layer_id."""

    entry = _find_registry_entry(
        registry,
        ui_layer_id,
    )

    if entry and entry.get("db_layer_id"):
        return str(entry["db_layer_id"])

    return None


def _get_basemap_reference_layer_id() -> str:
    """Find the registered OpenStreetMap reference layer."""

    for layer in _LAYER_STORE.list():
        if (
            layer.get("layer_type") == "reference"
            and layer.get("source_type") == "basemap"
            and layer.get("filename") == "OpenStreetMap"
        ):
            return str(layer["layer_id"])

    raise ValueError(
        "The OpenStreetMap basemap is not registered in the database."
    )


def _raster_path_from_entry(entry: dict) -> Path:
    """Return the historical COG path from a layer registry entry."""

    value = entry.get("cog_path")

    if not value:
        raise ValueError(
            "Historical layer does not contain a COG path."
        )

    path = Path(value)

    if not path.exists():
        raise FileNotFoundError(
            f"Historical raster not found: {path}"
        )

    return path


def _historical_pixel_line(
    historical_position: dict,
    historical_entry: dict,
) -> tuple[float, float]:
    """Convert WGS84 lon/lat to historical raster pixel/line.

    rasterio.dataset.index() returns row/column. GDAL GCP order is
    pixel/line, i.e. column/x first and row/y second.
    """

    raster_path = _raster_path_from_entry(
        historical_entry
    )

    lon = float(historical_position["lon"])
    lat = float(historical_position["lat"])

    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(
                "Historical raster has no CRS."
            )

        # Leaflet position is WGS84. Transform to the actual raster CRS.
        from pyproj import Transformer

        transformer = Transformer.from_crs(
            "EPSG:4326",
            src.crs,
            always_xy=True,
        )

        raster_x, raster_y = transformer.transform(
            lon,
            lat,
        )

        row, col = src.index(
            raster_x,
            raster_y,
        )

        # dataset.index() returns integer row/column. Convert the pixel
        # center to continuous pixel/line coordinates for GDAL.
        if (
            row < 0
            or row >= src.height
            or col < 0
            or col >= src.width
        ):
            raise ValueError(
                "The selected historical point is outside "
                "the historical raster."
            )

        # Convert raster cell index to pixel/line position using the
        # affine transform. Pixel/line values correspond to raster
        # coordinates; use the clicked map position projected into the
        # raster CRS for sub-pixel precision.
        inv_transform = ~src.transform
        pixel_x, pixel_y = inv_transform * (
            raster_x,
            raster_y,
        )

        return float(pixel_x), float(pixel_y)


def register_gcp_callbacks(app, store: GCPStore):
    """Register all GCP interaction callbacks."""

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
        pending,
        records,
        collection_active,
        reference_layer_ui_id,
        historical_layer_ui_id,
        reference_registry,
        historical_registry,
    ):
        del add_clicks, confirm_clicks, cancel_clicks

        records = records or []
        collection_active = bool(collection_active)
        triggered = ctx.triggered_id

        button_label = (
            "Stop GCP"
            if collection_active
            else "Add GCP"
        )

        # -------------------------------------------------
        # TOGGLE COLLECTION MODE
        # -------------------------------------------------

        if triggered == "add-gcp-button":
            collection_active = not collection_active

            if collection_active:
                status = (
                    _format_pending_status(pending)
                    if pending
                    else (
                        "GCP collection active — "
                        "click a point on the reference map."
                    )
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

            status = (
                _format_pending_status(pending)
                + " | Collection paused."
                if pending
                else (
                    "GCP collection inactive — "
                    "click Add GCP to start."
                )
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

        # -------------------------------------------------
        # CLICK REFERENCE MAP
        # -------------------------------------------------

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
                    button_label,
                )

            if pending:
                return (
                    no_update,
                    no_update,
                    "A GCP is already pending. "
                    "Confirm or cancel it first.",
                    False,
                    False,
                    True,
                    collection_active,
                    button_label,
                )

            click_position = _extract_click_position(
                reference_click
            )

            if click_position is None:
                return (
                    no_update,
                    no_update,
                    "Could not read the clicked map position.",
                    True,
                    True,
                    True,
                    collection_active,
                    button_label,
                )

            # A reference layer is optional in the UI because the base map
            # itself is a valid registered reference source.
            reference_db_id = _get_db_layer_id(
                reference_registry,
                reference_layer_ui_id,
                layer_type="reference",
            )

            if reference_db_id is None:
                reference_db_id = (
                    _get_basemap_reference_layer_id()
                )

            historical_entry = _find_registry_entry(
                historical_registry,
                historical_layer_ui_id,
            )

            if historical_entry is None:
                return (
                    no_update,
                    no_update,
                    (
                        "Upload a historical map before "
                        "collecting GCPs."
                    ),
                    True,
                    True,
                    True,
                    collection_active,
                    button_label,
                )

            # The initial historical marker is placed at the same geographic
            # position as the reference click. Validate that this position is
            # actually inside the historical raster.
            reference = _pending_position(click_position)

            try:
                _historical_pixel_line(
                    reference,
                    historical_entry,
                )
            except (ValueError, FileNotFoundError) as exc:
                return (
                    no_update,
                    no_update,
                    str(exc),
                    True,
                    True,
                    True,
                    collection_active,
                    button_label,
                )

            pending = {
                "reference": reference,
                "historical": dict(reference),
                "reference_layer_id": str(reference_db_id),
                "historical_layer_id": str(
                    historical_entry["db_layer_id"]
                ),
            }

            return (
                pending,
                records,
                _format_pending_status(pending),
                False,
                False,
                True,
                collection_active,
                button_label,
            )

        # -------------------------------------------------
        # DRAG HISTORICAL MARKER
        # -------------------------------------------------

        if triggered == "gcp-drag-event":
            drag_position = _extract_drag_position(
                drag_event
            )

            if not pending or drag_position is None:
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    True,
                    collection_active,
                    button_label,
                )

            historical = _pending_position(
                drag_position
            )

            historical_entry = _find_registry_entry(
                historical_registry,
                historical_layer_ui_id,
            )

            if historical_entry is None:
                return (
                    no_update,
                    no_update,
                    "Historical layer is no longer available.",
                    False,
                    False,
                    True,
                    collection_active,
                    button_label,
                )

            try:
                _historical_pixel_line(
                    historical,
                    historical_entry,
                )
            except (ValueError, FileNotFoundError) as exc:
                return (
                    no_update,
                    no_update,
                    str(exc),
                    False,
                    False,
                    True,
                    collection_active,
                    button_label,
                )

            pending = {
                **pending,
                "historical": historical,
            }

            return (
                pending,
                records,
                _format_pending_status(pending),
                False,
                False,
                True,
                collection_active,
                button_label,
            )

        # -------------------------------------------------
        # CONFIRM CURRENT GCP
        # -------------------------------------------------

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
                    button_label,
                )

            reference = _pending_position(
                pending["reference"]
            )
            historical = _pending_position(
                pending["historical"]
            )

            historical_entry = _find_registry_entry(
                historical_registry,
                historical_layer_ui_id,
            )

            if historical_entry is None:
                return (
                    no_update,
                    no_update,
                    "Historical layer is no longer available.",
                    False,
                    False,
                    True,
                    collection_active,
                    button_label,
                )

            try:
                historical_pixel, historical_line = (
                    _historical_pixel_line(
                        historical,
                        historical_entry,
                    )
                )
            except (ValueError, FileNotFoundError) as exc:
                return (
                    no_update,
                    no_update,
                    str(exc),
                    False,
                    False,
                    True,
                    collection_active,
                    button_label,
                )

            reference_db_id = pending.get(
                "reference_layer_id"
            )

            historical_db_id = pending.get(
                "historical_layer_id"
            )

            if not reference_db_id:
                reference_db_id = (
                    _get_basemap_reference_layer_id()
                )

            if not historical_db_id:
                historical_db_id = (
                    historical_entry.get("db_layer_id")
                )

            if not historical_db_id:
                return (
                    no_update,
                    no_update,
                    "Historical layer has no database layer ID.",
                    False,
                    False,
                    True,
                    collection_active,
                    button_label,
                )

            try:
                student_id = int(GCP_STUDENT_ID)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "GCP_STUDENT_ID must contain a valid user_id."
                ) from exc

            record = build_gcp_record(
                reference_position=[
                    reference["lat"],
                    reference["lon"],
                ],
                historical_position=[
                    historical["lat"],
                    historical["lon"],
                ],
                historical_pixel=historical_pixel,
                historical_line=historical_line,
                student_id=student_id,
                reference_layer_id=reference_db_id,
                historical_layer_id=historical_db_id,
            )

            saved = store.create(record)
            records = store.list()

            status = (
                f"Confirmed {saved['gcp_id']} — "
                f"offset: {saved['offset_m']:.2f} m | "
                "Ready for next point."
            )

            return (
                None,
                records,
                status,
                True,
                True,
                True,
                collection_active,
                button_label,
            )

        # -------------------------------------------------
        # CANCEL CURRENT GCP
        # -------------------------------------------------

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
                button_label,
            )

        return (
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            True,
            collection_active,
            button_label,
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
    def render_gcp_state(
        records,
        pending,
        selected_gcp_id,
    ):
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

        rows = [
            gcp_table_row(record)
            for record in records
        ]

        return (
            reference_children,
            historical_children,
            rows,
        )

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

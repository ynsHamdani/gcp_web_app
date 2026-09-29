from __future__ import annotations

"""Dash workflow for Ground Control Point collection and deletion."""

from pathlib import Path

import rasterio
from dash import Input, Output, State, ctx, no_update
from pyproj import Transformer

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


# The layers table is shared by reference and historical layers.
_LAYER_STORE = PostgresLayerStore(get_db_pool())


# =========================================================
# HELPERS
# =========================================================


def _format_pending_status(pending: dict) -> str:
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
    if isinstance(position, dict):
        lat = position.get("lat")
        lon = position.get("lon", position.get("lng"))
        if lat is None or lon is None:
            raise ValueError("Invalid Leaflet coordinate dictionary.")
        position = [lat, lon]

    return normalize_position(position)


def _extract_click_position(click_data):
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


def _registry_entry(registry, ui_layer_id):
    if not ui_layer_id:
        return None

    value = str(ui_layer_id)
    return next(
        (
            item
            for item in (registry or [])
            if str(item.get("id")) == value
        ),
        None,
    )


def _db_layer_id_from_registry(
    registry,
    ui_layer_id,
    expected_layer_type: str,
) -> int | None:
    """Resolve a UI layer ID to the numeric layers.layer_id."""

    entry = _registry_entry(registry, ui_layer_id)
    if entry:
        if entry.get("db_layer_id") is not None:
            return int(entry["db_layer_id"])

        ui_id = str(entry.get("id", ""))
        layers = _LAYER_STORE.list()

        # Current raster registries use the SHA-256/cog stem as the UI ID.
        match = next(
            (
                layer
                for layer in layers
                if layer["layer_type"] == expected_layer_type
                and (
                    str(layer.get("sha256")) == ui_id
                    or str(layer.get("layer_id")) == ui_id
                )
            ),
            None,
        )

        if match:
            return int(match["layer_id"])

    # Also accept a numeric selector directly when one is supplied.
    try:
        candidate = int(str(ui_layer_id))
    except (TypeError, ValueError):
        return None

    layer = _LAYER_STORE.get(candidate)
    if layer and layer["layer_type"] == expected_layer_type:
        return candidate

    return None


def _get_basemap_reference_layer_id() -> int:
    """Return/create the OpenStreetMap reference layer row."""

    layers = _LAYER_STORE.list()
    existing = next(
        (
            layer
            for layer in layers
            if layer["layer_type"] == "reference"
            and layer["source_type"] == "basemap"
            and layer["filename"] == "OpenStreetMap"
        ),
        None,
    )

    if existing:
        return int(existing["layer_id"])

    created = _LAYER_STORE.upsert(
        {
            "layer_type": "reference",
            "source_type": "basemap",
            "filename": "OpenStreetMap",
            "sha256": None,
            "crs": "EPSG:3857",
            "extent": [
                -20037508.342789244,
                -20037508.342789244,
                20037508.342789244,
                20037508.342789244,
            ],
            "width": None,
            "height": None,
        }
    )

    return int(created["layer_id"])


def _historical_pixel_line(
    registry,
    ui_layer_id,
    position: dict,
) -> tuple[float, float]:
    """Compute continuous raster pixel/line for a historical point."""

    entry = _registry_entry(registry, ui_layer_id)
    if entry is None:
        raise ValueError("The selected historical layer is unavailable.")

    cog_path = entry.get("cog_path")
    if not cog_path:
        raise ValueError(
            "The selected historical layer has no server-side COG path."
        )

    path = Path(cog_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Historical COG not found: {path}"
        )

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError("Historical raster has no CRS.")

        transformer = Transformer.from_crs(
            "EPSG:4326",
            dataset.crs,
            always_xy=True,
        )
        x, y = transformer.transform(
            float(position["lon"]),
            float(position["lat"]),
        )

        left, bottom, right, top = dataset.bounds
        tolerance_x = abs(dataset.transform.a) * 0.5
        tolerance_y = abs(dataset.transform.e) * 0.5

        if not (
            left - tolerance_x <= x <= right + tolerance_x
            and bottom - tolerance_y <= y <= top + tolerance_y
        ):
            raise ValueError(
                "The historical GCP point is outside the selected raster."
            )

        pixel, line = (~dataset.transform) * (x, y)

        if not (0.0 <= pixel < dataset.width and 0.0 <= line < dataset.height):
            raise ValueError(
                "The historical GCP point is outside the raster pixels."
            )

        return float(pixel), float(line)


def _resolve_layer_ids(
    pending: dict,
    reference_registry,
    historical_registry,
) -> tuple[int, int]:
    """Resolve required numeric FK IDs for a pending GCP."""

    reference_ui_id = pending.get("reference_layer_id")
    historical_ui_id = pending.get("historical_layer_id")

    reference_db_id = _db_layer_id_from_registry(
        reference_registry,
        reference_ui_id,
        expected_layer_type="reference",
    )

    if reference_db_id is None:
        # OpenStreetMap is the default/fallback reference source.
        reference_db_id = _get_basemap_reference_layer_id()

    historical_db_id = _db_layer_id_from_registry(
        historical_registry,
        historical_ui_id,
        expected_layer_type="historical",
    )

    if historical_db_id is None:
        raise ValueError(
            "A valid historical layer must be selected before confirming a GCP."
        )

    if reference_db_id == historical_db_id:
        raise ValueError(
            "Reference and historical layers must be different."
        )

    return reference_db_id, historical_db_id


def _no_change_return(
    collection_active,
    *,
    status=no_update,
    confirm_disabled=no_update,
    cancel_disabled=no_update,
    selected_id=no_update,
    delete_disabled=no_update,
):
    return (
        no_update,
        no_update,
        status,
        confirm_disabled,
        cancel_disabled,
        True,
        collection_active,
        "Stop GCP" if collection_active else "Add GCP",
        selected_id,
        delete_disabled,
    )


# =========================================================
# CALLBACKS
# =========================================================


def register_gcp_callbacks(app, store: GCPStore):
    """Register GCP collection, selection, and deletion callbacks."""

    @app.callback(
        Output("gcp-pending", "data"),
        Output("gcp-records", "data"),
        Output("gcp-status", "children"),
        Output("confirm-gcp-button", "disabled"),
        Output("cancel-gcp-button", "disabled"),
        Output("gcp-drag-event", "clear_data"),
        Output("gcp-collection-active", "data"),
        Output("add-gcp-button", "children"),
        Output("gcp-selected-id", "data"),
        Output("delete-gcp-button", "disabled"),
        Input("add-gcp-button", "n_clicks"),
        Input("reference-map", "clickData"),
        Input("gcp-drag-event", "data"),
        Input("confirm-gcp-button", "n_clicks"),
        Input("cancel-gcp-button", "n_clicks"),
        Input("gcp-table", "selectedRows"),
        Input("delete-gcp-button", "n_clicks"),
        State("gcp-pending", "data"),
        State("gcp-records", "data"),
        State("gcp-collection-active", "data"),
        State("gcp-selected-id", "data"),
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
        selected_rows,
        delete_clicks,
        pending,
        records,
        collection_active,
        selected_gcp_id,
        reference_layer_id,
        historical_layer_id,
        reference_registry,
        historical_registry,
    ):
        del add_clicks, confirm_clicks, cancel_clicks, delete_clicks

        records = records or []
        selected_rows = selected_rows or []
        collection_active = bool(collection_active)
        triggered = ctx.triggered_id

        # -------------------------------------------------
        # Table selection
        # -------------------------------------------------
        if triggered == "gcp-table":
            if not selected_rows:
                return _no_change_return(
                    collection_active,
                    selected_id=None,
                    delete_disabled=True,
                )

            selected_id = selected_rows[0].get("gcp_id")
            if not selected_id:
                return _no_change_return(
                    collection_active,
                    selected_id=None,
                    delete_disabled=True,
                )

            return _no_change_return(
                collection_active,
                selected_id=selected_id,
                delete_disabled=False,
            )

        # -------------------------------------------------
        # Delete selected GCP
        # -------------------------------------------------
        if triggered == "delete-gcp-button":
            gcp_id = selected_gcp_id
            if not gcp_id and selected_rows:
                gcp_id = selected_rows[0].get("gcp_id")

            if not gcp_id:
                return _no_change_return(
                    collection_active,
                    status="Select a GCP in the table first.",
                    selected_id=None,
                    delete_disabled=True,
                )

            try:
                student_id = int(GCP_STUDENT_ID)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "GCP_STUDENT_ID must contain a valid user_id."
                ) from exc

            try:
                store.delete(
                    gcp_id,
                    requester_id=student_id,
                    requester_role="student",
                )
            except PermissionError:
                return _no_change_return(
                    collection_active,
                    status=f"You are not allowed to delete {gcp_id}.",
                    selected_id=gcp_id,
                    delete_disabled=False,
                )
            except KeyError as exc:
                return _no_change_return(
                    collection_active,
                    status=str(exc),
                    selected_id=None,
                    delete_disabled=True,
                )

            records = store.list()

            return (
                None,
                records,
                f"Deleted {gcp_id}.",
                True,
                True,
                True,
                collection_active,
                "Stop GCP" if collection_active else "Add GCP",
                None,
                True,
            )

        # -------------------------------------------------
        # Toggle collection mode
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
                    selected_gcp_id,
                    not bool(selected_gcp_id),
                )

            status = (
                _format_pending_status(pending) + " | Collection paused."
                if pending
                else "GCP collection inactive — click Add GCP to start."
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
                selected_gcp_id,
                not bool(selected_gcp_id),
            )

        # -------------------------------------------------
        # Reference map click
        # -------------------------------------------------
        if triggered == "reference-map":
            if not collection_active:
                return _no_change_return(
                    collection_active,
                    status=(
                        "GCP collection inactive — "
                        "click Add GCP before selecting a point."
                    ),
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            if pending:
                return _no_change_return(
                    collection_active,
                    status=(
                        "A GCP is already pending. "
                        "Confirm or cancel it first."
                    ),
                    confirm_disabled=False,
                    cancel_disabled=False,
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            click_position = _extract_click_position(reference_click)
            if click_position is None:
                return _no_change_return(
                    collection_active,
                    status="Could not read the clicked map position.",
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            reference = _pending_position(click_position)

            # Validate the historical layer at the initial reference point.
            historical_entry = _registry_entry(
                historical_registry,
                historical_layer_id,
            )
            if historical_entry is None:
                return _no_change_return(
                    collection_active,
                    status=(
                        "Select a historical map before collecting GCPs."
                    ),
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            try:
                _historical_pixel_line(
                    historical_registry,
                    historical_layer_id,
                    reference,
                )
            except Exception as exc:
                return _no_change_return(
                    collection_active,
                    status=f"Cannot create GCP here: {exc}",
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            pending = {
                "reference": reference,
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
                selected_gcp_id,
                not bool(selected_gcp_id),
            )

        # -------------------------------------------------
        # Historical marker drag
        # -------------------------------------------------
        if triggered == "gcp-drag-event":
            drag_position = _extract_drag_position(drag_event)

            if not pending or drag_position is None:
                return _no_change_return(
                    collection_active,
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            try:
                _historical_pixel_line(
                    historical_registry,
                    pending.get("historical_layer_id"),
                    _pending_position(drag_position),
                )
            except Exception as exc:
                return _no_change_return(
                    collection_active,
                    status=f"Invalid historical position: {exc}",
                    confirm_disabled=False,
                    cancel_disabled=False,
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
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
                "Stop GCP",
                selected_gcp_id,
                not bool(selected_gcp_id),
            )

        # -------------------------------------------------
        # Confirm current GCP
        # -------------------------------------------------
        if triggered == "confirm-gcp-button":
            if not pending:
                return _no_change_return(
                    collection_active,
                    status="No pending GCP to confirm.",
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            try:
                student_id = int(GCP_STUDENT_ID)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "GCP_STUDENT_ID must contain a valid user_id."
                ) from exc

            try:
                reference_db_id, historical_db_id = _resolve_layer_ids(
                    pending,
                    reference_registry,
                    historical_registry,
                )

                pixel, line = _historical_pixel_line(
                    historical_registry,
                    pending.get("historical_layer_id"),
                    pending["historical"],
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
                    historical_pixel=pixel,
                    historical_line=line,
                    student_id=str(student_id),
                    reference_layer_id=str(reference_db_id),
                    historical_layer_id=str(historical_db_id),
                )

                saved = store.create(record)
                records = store.list()

            except Exception as exc:
                return _no_change_return(
                    collection_active,
                    status=f"Could not confirm GCP: {exc}",
                    confirm_disabled=False,
                    cancel_disabled=False,
                    selected_id=selected_gcp_id,
                    delete_disabled=not bool(selected_gcp_id),
                )

            status = (
                f"Confirmed {saved['gcp_id']} — "
                f"offset: {saved['offset_m']:.2f} m"
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
                None,
                True,
            )

        # -------------------------------------------------
        # Cancel current GCP
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
                "Stop GCP" if collection_active else "Add GCP",
                selected_gcp_id,
                not bool(selected_gcp_id),
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
            selected_gcp_id,
            not bool(selected_gcp_id),
        )

    # -----------------------------------------------------
    # Render markers + table
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

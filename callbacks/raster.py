from __future__ import annotations

"""Dash callbacks and Flask routes for temporary raster uploads.

The browser keeps an active layer registry for the current page. In parallel,
this module persists durable layer metadata to a JSON LayerStore. The latter
contains filename, SHA-256, CRS, extent, width and height and is independent
of the temporary COG cache.
"""

from dash import Input, Output, State, no_update
from flask import send_file

from config import (
    TEMP_RASTER_DIR,
    TEMP_RASTER_TTL_HOURS,
    APP_BASE_URL,
    TITILER_URL,
)
from maps.map_views import build_layer_children
from maps.raster import (
    calculate_fit_zoom,
    cleanup_expired_temp_rasters,
    get_raster_metadata,
    prepare_uploaded_raster,
)
from models.layer import build_layer_record
from storage.layer_store import LayerStore


# =========================================================
# ROUTES
# =========================================================


def register_raster_routes(app):
    """Register temporary-raster routes used by TiTiler."""

    @app.server.route("/raster/<path:relative_path>")
    def serve_temp_raster(relative_path):
        """Serve one temporary COG and refresh its TTL timestamp."""

        from maps.raster import (
            get_temp_raster_path,
            touch_cached_raster_from_relative_path,
        )

        try:
            touch_cached_raster_from_relative_path(relative_path)
            path = get_temp_raster_path(relative_path)
        except (ValueError, FileNotFoundError):
            return ("Raster not found.", 404)

        return send_file(
            path,
            conditional=True,
        )


# =========================================================
# HELPERS
# =========================================================


def _layer_options(layer_registry):
    """Convert active browser registry entries into dropdown options."""

    return [
        {
            "label": item["name"],
            "value": item["id"],
        }
        for item in (layer_registry or [])
    ]


def _update_registry(layer_registry, new_entry):
    """Replace an active entry with the same ID, otherwise append it."""

    registry = [
        item
        for item in (layer_registry or [])
        if item.get("id") != new_entry["id"]
    ]

    registry.append(new_entry)
    return registry


def _raster_entry(
    asset,
    filename,
    opacity_percent,
    metadata,
):
    """Create the active browser layer entry."""

    opacity = (
        float(opacity_percent) / 100.0
        if opacity_percent is not None
        else 1.0
    )

    # The SHA-256 directory/file stem is the stable layer identity.
    layer_id = asset.cog_path.stem

    return {
        # Existing browser-registry keys.
        "id": layer_id,
        "name": filename,
        "original_path": "",
        "cog_path": str(asset.cog_path),
        "tile_url": asset.tile_url,
        "bounds": asset.bounds,
        "center": asset.center,
        "zoom": calculate_fit_zoom(asset.bounds),
        "minzoom": asset.minzoom,
        "maxzoom": asset.maxzoom,
        "opacity": opacity,

        # Persistent layer metadata.
        "layer_id": layer_id,
        "filename": filename,
        "sha256": layer_id,
        "crs": metadata["crs"],
        "extent": metadata["extent"],
        "width": metadata["width"],
        "height": metadata["height"],
    }


def _persist_layer(layer_store: LayerStore, asset, filename: str):
    """Persist layer metadata while keeping the raster itself temporary."""

    metadata = get_raster_metadata(asset.cog_path)
    layer_id = asset.cog_path.stem

    record = build_layer_record(
        layer_id=layer_id,
        filename=filename,
        sha256=layer_id,
        crs=metadata["crs"],
        extent=metadata["extent"],
        width=metadata["width"],
        height=metadata["height"],
    )

    return layer_store.upsert(record), metadata


# =========================================================
# CALLBACKS
# =========================================================


def register_raster_callbacks(
    app,
    reference_layer_store: LayerStore,
    historical_layer_store: LayerStore,
):
    """Register reference and historical upload callbacks."""

    cleanup_expired_temp_rasters(TEMP_RASTER_TTL_HOURS)

    # -----------------------------------------------------
    # REFERENCE UPLOAD
    # -----------------------------------------------------

    @app.callback(
        Output("reference-layer-control", "children"),
        Output("reference-upload-status", "children"),
        Output("reference-layer-registry", "data"),
        Output("reference-layer-zoom-select", "options"),
        Output("reference-layer-zoom-select", "value"),
        Input("reference-upload", "contents"),
        State("reference-upload", "filename"),
        State("reference-layer-registry", "data"),
        State("reference-opacity", "value"),
        prevent_initial_call=True,
    )
    def handle_reference_upload(
        contents,
        filename,
        layer_registry,
        reference_opacity,
    ):
        if not contents:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )

        try:
            asset = prepare_uploaded_raster(
                contents=contents,
                filename=filename,
                raster_kind="reference",
            )

            persistent_record, metadata = _persist_layer(
                reference_layer_store,
                asset,
                filename,
            )

            entry = _raster_entry(
                asset,
                filename,
                reference_opacity,
                metadata,
            )

            # Keep the browser registry shape compatible with existing
            # navigation/GCP callbacks.
            entry["id"] = persistent_record["layer_id"]

            registry = _update_registry(
                layer_registry,
                entry,
            )

            children = build_layer_children(
                registry,
                "reference-raster-layer",
            )

            options = _layer_options(registry)

            return (
                children,
                f"Loaded: {filename}",
                registry,
                options,
                entry["id"],
            )

        except Exception as exc:
            return (
                no_update,
                f"Upload failed: {exc}",
                no_update,
                no_update,
                no_update,
            )

    # -----------------------------------------------------
    # HISTORICAL UPLOAD
    # -----------------------------------------------------

    @app.callback(
        Output("historical-layer-control", "children"),
        Output("historical-upload-status", "children"),
        Output("historical-layer-registry", "data"),
        Output("historical-layer-zoom-select", "options"),
        Output("historical-layer-zoom-select", "value"),
        Input("historical-upload", "contents"),
        State("historical-upload", "filename"),
        State("historical-layer-registry", "data"),
        State("historical-opacity", "value"),
        prevent_initial_call=True,
    )
    def handle_historical_upload(
        contents,
        filename,
        layer_registry,
        historical_opacity,
    ):
        if not contents:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )

        try:
            asset = prepare_uploaded_raster(
                contents=contents,
                filename=filename,
                raster_kind="historical",
            )

            persistent_record, metadata = _persist_layer(
                historical_layer_store,
                asset,
                filename,
            )

            entry = _raster_entry(
                asset,
                filename,
                historical_opacity,
                metadata,
            )

            entry["id"] = persistent_record["layer_id"]

            registry = _update_registry(
                layer_registry,
                entry,
            )

            children = build_layer_children(
                registry,
                "historical-raster-layer",
            )

            options = _layer_options(registry)

            return (
                children,
                f"Loaded: {filename}",
                registry,
                options,
                entry["id"],
            )

        except Exception as exc:
            return (
                no_update,
                f"Upload failed: {exc}",
                no_update,
                no_update,
                no_update,
            )

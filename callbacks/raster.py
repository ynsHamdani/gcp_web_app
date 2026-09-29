from __future__ import annotations

"""Dash callbacks and Flask routes for temporary raster uploads.

The browser/UI keeps the SHA-256 value as its temporary layer identity.
PostgreSQL has its own BIGINT layer_id. This module registers every uploaded
raster in PostgreSQL and stores both identities in the Dash layer registry:

    id           -> SHA-256 / temporary raster identity used by the UI
    db_layer_id  -> PostgreSQL layers.layer_id used by GCP foreign keys
"""

from pathlib import Path

import rasterio
from dash import Input, Output, State, no_update
from flask import send_file

from config import (
    APP_BASE_URL,
    GCP_CRS,
    TEMP_RASTER_DIR,
    TEMP_RASTER_TTL_HOURS,
    TITILER_URL,
)
from database.db import get_db_pool
from maps.map_views import build_layer_children
from maps.raster import (
    calculate_fit_zoom,
    cleanup_expired_temp_rasters,
    prepare_uploaded_raster,
)
from storage.layer_store import PostgresLayerStore


# =========================================================
# DATABASE LAYER STORE
# =========================================================

_layer_store = PostgresLayerStore(get_db_pool())
_basemap_db_layer_id: str | None = None


def _ensure_basemap_layer() -> dict:
    """Return the registered OpenStreetMap reference layer.

    The basemap is represented as a normal row in the layers table, so every
    GCP can always have a non-null reference_layer_id.
    """

    global _basemap_db_layer_id

    if _basemap_db_layer_id is not None:
        existing = _layer_store.get(_basemap_db_layer_id)
        if existing is not None:
            return existing

    for layer in _layer_store.list():
        if (
            layer.get("layer_type") == "reference"
            and layer.get("source_type") == "basemap"
            and layer.get("filename") == "OpenStreetMap"
        ):
            _basemap_db_layer_id = str(layer["layer_id"])
            return layer

    # Web Mercator world extent. Width/height are intentionally unknown for
    # a slippy-map basemap and are therefore stored as NULL.
    basemap = _layer_store.upsert(
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

    _basemap_db_layer_id = str(basemap["layer_id"])
    return basemap


def _layer_record_from_raster(
    asset,
    filename: str,
    layer_type: str,
) -> dict:
    """Build a PostgreSQL layer record from the prepared COG."""

    with rasterio.open(asset.cog_path) as src:
        if src.crs is None:
            raise ValueError(
                f"Raster '{filename}' has no CRS."
            )

        return {
            "layer_type": layer_type,
            "source_type": "uploaded",
            "filename": filename,
            # prepare_uploaded_raster uses the SHA-256 as the COG stem.
            "sha256": asset.cog_path.stem,
            "crs": src.crs.to_string(),
            "extent": [
                float(src.bounds.left),
                float(src.bounds.bottom),
                float(src.bounds.right),
                float(src.bounds.top),
            ],
            "width": int(src.width),
            "height": int(src.height),
        }


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
    """Convert registry entries into Dash dropdown options."""

    return [
        {
            "label": item["name"],
            "value": item["id"],
        }
        for item in (layer_registry or [])
    ]


def _update_registry(layer_registry, new_entry):
    """Replace an entry with the same SHA identity, otherwise append it."""

    registry = [
        item
        for item in (layer_registry or [])
        if item.get("id") != new_entry["id"]
    ]

    registry.append(new_entry)
    return registry


def _raster_entry(asset, filename, opacity_percent, db_layer_id):
    """Create the UI registry entry for one raster layer."""

    opacity = (
        float(opacity_percent) / 100.0
        if opacity_percent is not None
        else 1.0
    )

    # Keep this SHA-based ID because existing map/navigation code depends on it.
    layer_id = asset.cog_path.stem

    return {
        "id": layer_id,
        "db_layer_id": str(db_layer_id),
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
    }


def _register_uploaded_layer(
    asset,
    filename: str,
    layer_type: str,
) -> dict:
    """Register/reuse an uploaded raster in PostgreSQL."""

    layer_record = _layer_record_from_raster(
        asset=asset,
        filename=filename,
        layer_type=layer_type,
    )

    return _layer_store.upsert(layer_record)


# =========================================================
# CALLBACKS
# =========================================================


def register_raster_callbacks(app):
    """Register reference and historical upload callbacks."""

    cleanup_expired_temp_rasters(TEMP_RASTER_TTL_HOURS)

    # Make the basemap available as a real reference layer before GCP
    # collection starts.
    try:
        _ensure_basemap_layer()
    except Exception:
        # Do not prevent the rest of the Dash application from starting.
        # A later GCP action will surface the database error clearly.
        pass

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

            db_layer = _register_uploaded_layer(
                asset=asset,
                filename=filename,
                layer_type="reference",
            )

            entry = _raster_entry(
                asset=asset,
                filename=filename,
                opacity_percent=reference_opacity,
                db_layer_id=db_layer["layer_id"],
            )

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

            db_layer = _register_uploaded_layer(
                asset=asset,
                filename=filename,
                layer_type="historical",
            )

            entry = _raster_entry(
                asset=asset,
                filename=filename,
                opacity_percent=historical_opacity,
                db_layer_id=db_layer["layer_id"],
            )

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

from __future__ import annotations

from urllib.parse import quote

from dash import Input, Output, State, no_update
from dash import ctx
from flask import send_from_directory

from config import (
    APP_BASE_URL,
    TITILER_URL,
    REFERENCE_ORIGINAL_DIR,
    REFERENCE_COG_DIR,
    HISTORICAL_ORIGINAL_DIR,
    HISTORICAL_COG_DIR,
)

from maps.map_views import build_layer_children
from maps.raster import (
    RasterAsset,
    calculate_fit_zoom,
    convert_to_cog,
    get_titiler_asset,
    save_uploaded_tiff,
    validate_geotiff,
)


# =========================================================
# ROUTES
# =========================================================

def register_raster_routes(app):
    """Register the Flask routes that make COGs reachable by TiTiler."""

    @app.server.route(
        "/raster/reference/<path:filename>"
    )
    def serve_reference_raster(filename):
        return send_from_directory(
            str(REFERENCE_COG_DIR),
            filename,
            conditional=True,
        )

    @app.server.route(
        "/raster/historical/<path:filename>"
    )
    def serve_historical_raster(filename):
        return send_from_directory(
            str(HISTORICAL_COG_DIR),
            filename,
            conditional=True,
        )


# =========================================================
# HELPERS
# =========================================================

def _upload_raster(
    contents,
    filename,
    original_dir,
    cog_dir,
    raster_route,
    opacity_percent,
):
    """Save, validate, convert and prepare one uploaded GeoTIFF."""

    if not contents or not filename:
        raise ValueError("No raster file was provided.")

    original_path = None
    cog_path = None

    try:
        original_path = save_uploaded_tiff(
            contents,
            filename,
            original_dir,
        )

        validate_geotiff(
            original_path
        )

        cog_path = (
            cog_dir
            / f"{original_path.stem}_cog.tif"
        )

        convert_to_cog(
            original_path,
            cog_path,
        )

        raster_url = (
            f"{APP_BASE_URL}"
            f"{raster_route}"
            f"{quote(cog_path.name)}"
        )

        (
            tile_url,
            bounds,
            minzoom,
            maxzoom,
        ) = get_titiler_asset(
            raster_url,
            TITILER_URL,
            cog_path,
        )

        asset = RasterAsset(
            name=filename,
            original_path=original_path,
            cog_path=cog_path,
            tile_url=tile_url,
            bounds=bounds,
            minzoom=minzoom,
            maxzoom=maxzoom,
        )

        opacity = (
            opacity_percent / 100.0
            if opacity_percent is not None
            else 1.0
        )

        entry = {
            "id": asset.cog_path.stem,
            "name": filename,
            "original_path": str(asset.original_path),
            "cog_path": str(asset.cog_path),
            "tile_url": asset.tile_url,
            "bounds": asset.bounds,
            "center": asset.center,
            "zoom": calculate_fit_zoom(
                asset.bounds
            ),
            "minzoom": asset.minzoom,
            "maxzoom": asset.maxzoom,
            "opacity": opacity,
        }

        return asset, entry

    except Exception:
        if original_path:
            original_path.unlink(
                missing_ok=True
            )

        if cog_path:
            cog_path.unlink(
                missing_ok=True
            )

        raise


def _update_registry(layer_registry, new_entry):
    """Replace an existing entry with the same id, otherwise append it."""

    registry = [
        item
        for item in (layer_registry or [])
        if item.get("id") != new_entry["id"]
    ]

    registry.append(new_entry)
    return registry


def _layer_options(layer_registry):
    return [
        {
            "label": item["name"],
            "value": item["id"],
        }
        for item in (layer_registry or [])
    ]


# =========================================================
# CALLBACKS
# =========================================================

def register_raster_callbacks(app):
    """Register reference and historical raster-upload callbacks."""

    @app.callback(
        Output(
            "reference-layer-control",
            "children",
        ),
        Output(
            "reference-upload-status",
            "children",
        ),
        Output(
            "reference-layer-registry",
            "data",
        ),
        Output(
            "reference-layer-zoom-select",
            "options",
        ),
        Output(
            "reference-layer-zoom-select",
            "value",
        ),
        Input(
            "reference-upload",
            "contents",
        ),
        State(
            "reference-upload",
            "filename",
        ),
        State(
            "reference-layer-registry",
            "data",
        ),
        State(
            "reference-opacity",
            "value",
        ),
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
            asset, entry = _upload_raster(
                contents=contents,
                filename=filename,
                original_dir=REFERENCE_ORIGINAL_DIR,
                cog_dir=REFERENCE_COG_DIR,
                raster_route="/raster/reference/",
                opacity_percent=reference_opacity,
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

    @app.callback(
        Output(
            "historical-layer-control",
            "children",
        ),
        Output(
            "historical-upload-status",
            "children",
        ),
        Output(
            "historical-layer-registry",
            "data",
        ),
        Output(
            "historical-layer-zoom-select",
            "options",
        ),
        Output(
            "historical-layer-zoom-select",
            "value",
        ),
        Input(
            "historical-upload",
            "contents",
        ),
        State(
            "historical-upload",
            "filename",
        ),
        State(
            "historical-layer-registry",
            "data",
        ),
        State(
            "historical-opacity",
            "value",
        ),
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
            asset, entry = _upload_raster(
                contents=contents,
                filename=filename,
                original_dir=HISTORICAL_ORIGINAL_DIR,
                cog_dir=HISTORICAL_COG_DIR,
                raster_route="/raster/historical/",
                opacity_percent=historical_opacity,
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

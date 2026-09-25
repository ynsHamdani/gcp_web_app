from __future__ import annotations

from urllib.parse import quote

import dash_leaflet as dl
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    State,
    Patch,
    ctx,
    no_update,
)
from dash_extensions.javascript import Namespace
from flask import send_from_directory


# =========================================================
# CONFIG
# =========================================================

from config import (
    APP_BASE_URL,
    TITILER_URL,
    REFERENCE_ORIGINAL_DIR,
    REFERENCE_COG_DIR,
    HISTORICAL_ORIGINAL_DIR,
    HISTORICAL_COG_DIR,
)


# =========================================================
# RASTER FUNCTIONS
# =========================================================

from maps.raster import (
    RasterAsset,
    save_uploaded_tiff,
    validate_geotiff,
    convert_to_cog,
    get_titiler_asset,
    calculate_fit_zoom,
)


# =========================================================
# MAP LAYERS
# =========================================================

from maps.reference import create_reference_layers

from maps.historical import (
    create_historical_layers,
    create_historical_overlay,
)


# =========================================================
# UI
# =========================================================

from ui.layout import create_layout


# =========================================================
# APPLICATION
# =========================================================

app = Dash(
    __name__,
    title="Historical Map GCP Collection",
    suppress_callback_exceptions=True,
)


# =========================================================
# MAP SETTINGS
# =========================================================

INITIAL_CENTER = [56.15, 10.20]
INITIAL_ZOOM = 7

MAP_STYLE = {
    "width": "100%",
    "height": "100%",
}


# =========================================================
# JAVASCRIPT NAMESPACE
# =========================================================

ns = Namespace(
    "gcpMapSync",
    "handlers",
)


# =========================================================
# REFERENCE MAP
# =========================================================

reference_map = dl.Map(
    id="reference-map",

    center=INITIAL_CENTER,
    zoom=INITIAL_ZOOM,

    eventHandlers={
        "load": ns("registerReference"),
        "mouseover": ns("registerReference"),
        "mousedown": ns("registerReference"),
        "moveend": ns("syncReference"),
        "zoomend": ns("syncReference"),
    },

    children=create_reference_layers(),

    style=MAP_STYLE,
)


# =========================================================
# HISTORICAL MAP
# =========================================================

historical_map = dl.Map(
    id="historical-map",

    center=INITIAL_CENTER,
    zoom=INITIAL_ZOOM,

    eventHandlers={
        "load": ns("registerHistorical"),
        "mouseover": ns("registerHistorical"),
        "mousedown": ns("registerHistorical"),
        "moveend": ns("syncHistorical"),
        "zoomend": ns("syncHistorical"),
    },

    children=create_historical_layers(),

    style=MAP_STYLE,
)


# =========================================================
# PAGE LAYOUT
# =========================================================

app.layout = create_layout(
    reference_map=reference_map,
    historical_map=historical_map,
)


# =========================================================
# FILE SERVING FOR TITILER
# =========================================================

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
# TIFF UPLOAD CALLBACK
# =========================================================

@app.callback(

    # -----------------------------------------------------
    # Reference raster
    # -----------------------------------------------------

    Output(
        "reference-raster-layer",
        "url",
    ),

    Output(
        "reference-raster-layer",
        "maxNativeZoom",
    ),

    # -----------------------------------------------------
    # Historical layers
    # -----------------------------------------------------

    Output(
        "historical-layer-control",
        "children",
    ),

    # -----------------------------------------------------
    # Reference map view
    # -----------------------------------------------------

    Output(
        "reference-map",
        "center",
    ),

    Output(
        "reference-map",
        "zoom",
    ),

    # -----------------------------------------------------
    # Historical map view
    # -----------------------------------------------------

    Output(
        "historical-map",
        "center",
    ),

    Output(
        "historical-map",
        "zoom",
    ),

    # -----------------------------------------------------
    # Upload status
    # -----------------------------------------------------

    Output(
        "reference-upload-status",
        "children",
    ),

    Output(
        "historical-upload-status",
        "children",
    ),

    # -----------------------------------------------------
    # Inputs
    # -----------------------------------------------------

    Input(
        "reference-upload",
        "contents",
    ),

    Input(
        "historical-upload",
        "contents",
    ),

    # -----------------------------------------------------
    # Filenames
    # -----------------------------------------------------

    State(
        "reference-upload",
        "filename",
    ),

    State(
        "historical-upload",
        "filename",
    ),

    prevent_initial_call=True,
)
def handle_raster_upload(
    reference_contents,
    historical_contents,
    reference_filename,
    historical_filename,
):

    triggered = ctx.triggered_id


    # =====================================================
    # REFERENCE TIFF
    # =====================================================

    if triggered == "reference-upload":

        original_path = None
        cog_path = None

        try:

            # -------------------------------------------------
            # Save original TIFF
            # -------------------------------------------------

            original_path = save_uploaded_tiff(
                reference_contents,
                reference_filename,
                REFERENCE_ORIGINAL_DIR,
            )

            # -------------------------------------------------
            # Validate
            # -------------------------------------------------

            validate_geotiff(
                original_path
            )

            # -------------------------------------------------
            # COG path
            # -------------------------------------------------

            cog_path = (
                REFERENCE_COG_DIR
                / f"{original_path.stem}_cog.tif"
            )

            # -------------------------------------------------
            # Convert TIFF -> COG
            # -------------------------------------------------

            convert_to_cog(
                original_path,
                cog_path,
            )

            # -------------------------------------------------
            # URL accessible by TiTiler
            # -------------------------------------------------

            raster_url = (
                f"{APP_BASE_URL}"
                f"/raster/reference/"
                f"{quote(cog_path.name)}"
            )

            # -------------------------------------------------
            # TiTiler metadata + tile URL
            # -------------------------------------------------

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

            # -------------------------------------------------
            # Raster asset
            # -------------------------------------------------

            asset = RasterAsset(
                name=reference_filename,
                original_path=original_path,
                cog_path=cog_path,
                tile_url=tile_url,
                bounds=bounds,
                minzoom=minzoom,
                maxzoom=maxzoom,
            )

            # -------------------------------------------------
            # Fit map to reference raster
            # -------------------------------------------------

            zoom = calculate_fit_zoom(
                asset.bounds
            )

            # -------------------------------------------------
            # Return
            # -------------------------------------------------

            return (

                asset.tile_url,                  # 1
                asset.maxzoom,                   # 2

                no_update,                       # 3 historical layers

                asset.center,                    # 4 reference center
                zoom,                            # 5 reference zoom

                asset.center,                    # 6 historical center
                zoom,                            # 7 historical zoom

                f"Loaded: {reference_filename}", # 8
                no_update,                       # 9
            )

        except Exception as exc:

            if original_path:
                original_path.unlink(
                    missing_ok=True
                )

            if cog_path:
                cog_path.unlink(
                    missing_ok=True
                )

            return (
                no_update,                       # 1
                no_update,                       # 2
                no_update,                       # 3
                no_update,                       # 4
                no_update,                       # 5
                no_update,                       # 6
                no_update,                       # 7
                f"Upload failed: {exc}",         # 8
                no_update,                       # 9
            )


    # =====================================================
    # HISTORICAL TIFF
    # =====================================================

    if triggered == "historical-upload":

        original_path = None
        cog_path = None

        try:

            # -------------------------------------------------
            # Save original TIFF
            # -------------------------------------------------

            original_path = save_uploaded_tiff(
                historical_contents,
                historical_filename,
                HISTORICAL_ORIGINAL_DIR,
            )

            # -------------------------------------------------
            # Validate
            # -------------------------------------------------

            validate_geotiff(
                original_path
            )

            # -------------------------------------------------
            # COG path
            # -------------------------------------------------

            cog_path = (
                HISTORICAL_COG_DIR
                / f"{original_path.stem}_cog.tif"
            )

            # -------------------------------------------------
            # Convert TIFF -> COG
            # -------------------------------------------------

            convert_to_cog(
                original_path,
                cog_path,
            )

            # -------------------------------------------------
            # URL accessible by TiTiler
            # -------------------------------------------------

            raster_url = (
                f"{APP_BASE_URL}"
                f"/raster/historical/"
                f"{quote(cog_path.name)}"
            )

            # -------------------------------------------------
            # TiTiler metadata + tile URL
            # -------------------------------------------------

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

            # -------------------------------------------------
            # Raster asset
            # -------------------------------------------------

            asset = RasterAsset(
                name=historical_filename,
                original_path=original_path,
                cog_path=cog_path,
                tile_url=tile_url,
                bounds=bounds,
                minzoom=minzoom,
                maxzoom=maxzoom,
            )

            # -------------------------------------------------
            # Calculate zoom for NEW historical image
            # -------------------------------------------------

            zoom = calculate_fit_zoom(
                asset.bounds
            )

            # -------------------------------------------------
            # Create new historical overlay
            # -------------------------------------------------

            new_layer = create_historical_overlay(
                asset=asset,
                filename=historical_filename,
                opacity=1.0,
            )

            # -------------------------------------------------
            # Append without replacing existing layers
            # -------------------------------------------------

            patched_layers = Patch()

            patched_layers.append(
                new_layer
            )

            # -------------------------------------------------
            # Set BOTH maps to the new raster extent
            # -------------------------------------------------
            #
            # Because both maps receive exactly the same
            # center and zoom in the same Dash update, the
            # existing JS synchronization should not fight
            # the new view.
            # -------------------------------------------------

            return (

                no_update,                         # 1
                no_update,                         # 2

                patched_layers,                     # 3

                asset.center,                       # 4
                zoom,                               # 5

                asset.center,                       # 6
                zoom,                               # 7

                no_update,                          # 8

                f"Loaded: {historical_filename}",   # 9
            )
        

        except Exception as exc:

            if original_path:
                original_path.unlink(
                    missing_ok=True
                )

            if cog_path:
                cog_path.unlink(
                    missing_ok=True
                )

            return (
                no_update,                          # 1
                no_update,                          # 2
                no_update,                          # 3
                no_update,                          # 4
                no_update,                          # 5
                no_update,                          # 6
                no_update,                          # 7
                no_update,                          # 8
                f"Upload failed: {exc}",            # 9
            )


    # =====================================================
    # FALLBACK
    # =====================================================

    return (
        no_update,      # 1
        no_update,      # 2
        no_update,      # 3
        no_update,      # 4
        no_update,      # 5
        no_update,      # 6
        no_update,      # 7
        no_update,      # 8
        no_update,      # 9
    )


# =========================================================
# REFERENCE OPACITY
# =========================================================

@app.callback(

    Output(
        "reference-raster-layer",
        "opacity",
    ),

    Input(
        "reference-opacity",
        "value",
    ),

    prevent_initial_call=True,
)
def update_reference_opacity(value):

    return value / 100.0


# =========================================================
# HISTORICAL OPACITY
# =========================================================

@app.callback(

    Output(
        {
            "type": "historical-raster-layer",
            "index": ALL,
        },
        "opacity",
    ),

    Input(
        "historical-opacity",
        "value",
    ),

    State(
        {
            "type": "historical-raster-layer",
            "index": ALL,
        },
        "id",
    ),

    prevent_initial_call=True,
)
def update_historical_opacity(
    value,
    layer_ids,
):

    opacity = value / 100.0

    return [
        opacity
        for _ in layer_ids
    ]


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
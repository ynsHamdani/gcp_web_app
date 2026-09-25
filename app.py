from urllib.parse import quote
from dash import Dash, Input, Output, State, ctx, no_update
from flask import send_from_directory
import dash_leaflet as dl
from dash_extensions.javascript import Namespace
from dash import (
    Dash,
    Input,
    Output,
    State,
    Patch,
    ctx,
    no_update,
    ALL
)

from config import (
    APP_BASE_URL,
    TITILER_URL,
    REFERENCE_ORIGINAL_DIR,
    REFERENCE_COG_DIR,
    HISTORICAL_ORIGINAL_DIR,
    HISTORICAL_COG_DIR,
)

from maps.raster import (
    RasterAsset,
    save_uploaded_tiff,
    validate_geotiff,
    convert_to_cog,
    get_titiler_asset,
    calculate_fit_zoom,
)

from maps.reference import create_reference_layers
from maps.historical import create_historical_layers

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
# JAVASCRIPT SYNCHRONIZATION
# =========================================================

ns = Namespace("gcpMapSync", "handlers")


# =========================================================
# MAPS
# =========================================================

reference_map = dl.Map(
    id="reference-map",
    center=INITIAL_CENTER,
    zoom=INITIAL_ZOOM,

    eventHandlers={
        "mouseover": ns("registerReference"),
        "mousedown": ns("registerReference"),
        "moveend": ns("syncReference"),
        "zoomend": ns("syncReference"),
    },

    children=create_reference_layers(),


    style=MAP_STYLE,
)


historical_map = dl.Map(
    id="historical-map",
    center=INITIAL_CENTER,
    zoom=INITIAL_ZOOM,

    eventHandlers={
        "mouseover": ns("registerHistorical"),
        "mousedown": ns("registerHistorical"),
        "moveend": ns("syncHistorical"),
        "zoomend": ns("syncHistorical"),
    },

    children=create_historical_layers(),

    style=MAP_STYLE,
)


# =========================================================
# PAGE
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
# TIFF UPLOADS
# =========================================================

@app.callback(

    # Reference raster
    Output("reference-raster-layer", "url"),
    Output("reference-raster-layer", "maxNativeZoom"),

    # Historical layers
    Output("historical-layer-control", "children"),

    # Reference map viewport
    Output("reference-map", "center"),
    Output("reference-map", "zoom"),

    # Historical map viewport
    Output("historical-map", "center"),
    Output("historical-map", "zoom"),

    # Status
    Output("reference-upload-status", "children"),
    Output("historical-upload-status", "children"),

    # Inputs
    Input("reference-upload", "contents"),
    Input("historical-upload", "contents"),

    # State
    State("reference-upload", "filename"),
    State("historical-upload", "filename"),
    State("historical-opacity", "value"),

    prevent_initial_call=True,
)
def handle_raster_upload(
    reference_contents,
    historical_contents,
    reference_filename,
    historical_filename,
    historical_opacity,
):

    triggered = ctx.triggered_id

    # =====================================================
    # REFERENCE TIFF
    # =====================================================

    if triggered == "reference-upload":

        original_path = None
        cog_path = None

        try:

            original_path = save_uploaded_tiff(
                reference_contents,
                reference_filename,
                REFERENCE_ORIGINAL_DIR,
            )

            validate_geotiff(
                original_path
            )

            cog_path = (
                REFERENCE_COG_DIR
                / f"{original_path.stem}_cog.tif"
            )

            convert_to_cog(
                original_path,
                cog_path,
            )

            raster_url = (
                f"{APP_BASE_URL}"
                f"/raster/reference/"
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
                name=reference_filename,
                original_path=original_path,
                cog_path=cog_path,
                tile_url=tile_url,
                bounds=bounds,
                minzoom=minzoom,
                maxzoom=maxzoom,
            )

            zoom = calculate_fit_zoom(
                asset.bounds
            )

            return (

                asset.tile_url,
                asset.maxzoom,

                no_update,

                asset.center,
                zoom,

                asset.center,
                zoom,

                f"Loaded: {reference_filename}",
                no_update,
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
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                f"Upload failed: {exc}",
                no_update,
            )


    # =====================================================
    # HISTORICAL TIFF
    # =====================================================

    if triggered == "historical-upload":

        original_path = None
        cog_path = None

        try:

            original_path = save_uploaded_tiff(
                historical_contents,
                historical_filename,
                HISTORICAL_ORIGINAL_DIR,
            )

            validate_geotiff(
                original_path
            )

            cog_path = (
                HISTORICAL_COG_DIR
                / f"{original_path.stem}_cog.tif"
            )

            convert_to_cog(
                original_path,
                cog_path,
            )

            raster_url = (
                f"{APP_BASE_URL}"
                f"/raster/historical/"
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
                name=historical_filename,
                original_path=original_path,
                cog_path=cog_path,
                tile_url=tile_url,
                bounds=bounds,
                minzoom=minzoom,
                maxzoom=maxzoom,
            )

            # -------------------------------------------------
            # Correct zoom for THIS new raster
            # -------------------------------------------------

            zoom = calculate_fit_zoom(
                asset.bounds
            )

            # -------------------------------------------------
            # Unique layer ID
            # -------------------------------------------------

            layer_id = {
                "type": "historical-raster-layer",
                "index": cog_path.stem,
            }

            # -------------------------------------------------
            # New historical layer
            # -------------------------------------------------

            new_layer = dl.Overlay(

                dl.TileLayer(
                    id=layer_id,
                    url=asset.tile_url,
                    opacity=(
                        historical_opacity / 100
                        if historical_opacity is not None
                        else 1.0
                    ),
                    tileSize=256,
                    maxZoom=24,
                    zIndex=10,
                ),

                name=historical_filename,
                checked=True,
            )

            # -------------------------------------------------
            # Append without recreating the map
            # -------------------------------------------------

            patched_layers = Patch()
            patched_layers.append(
                new_layer
            )

            return (
                no_update,                         # 1
                no_update,                         # 2
                patched_layers,                    # 3

                asset.center,                      # 4
                zoom,                              # 5

                asset.center,                      # 6
                zoom,                              # 7

                no_update,                         # 8
                f"Loaded: {historical_filename}",  # 9
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
                no_update,  # 1
                no_update,  # 2
                no_update,  # 3
                no_update,  # 4
                no_update,  # 5
                no_update,  # 6
                no_update,  # 7
                no_update,  # 8
                f"Upload failed: {exc}",  # 9
            )

    return (
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
        no_update,
    )



@app.callback(
    Output("reference-raster-layer", "opacity"),
    Input("reference-opacity", "value"),
    prevent_initial_call=True,
)
def update_reference_opacity(value):
    return value / 100


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
    app.run(debug=True)
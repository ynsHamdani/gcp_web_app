from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import dash_leaflet as dl
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    State,
    ctx,
    dcc,
    html,
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
# HISTORICAL BASE MAP
# =========================================================

HISTORICAL_BASE_URL = (
    "https://{s}.tile.openstreetmap.org/"
    "{z}/{x}/{y}.png"
)


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
# HISTORICAL LAYER ZOOM CONTROL
# =========================================================
#
# Placed at the bottom-right so it does not cover the
# historical upload button at the top of the panel.
# =========================================================

zoom_control = html.Div(
    [
        html.Div(
            "Zoom to historical layer",
            style={
                "fontWeight": "600",
                "marginBottom": "6px",
            },
        ),

        dcc.Dropdown(
            id="historical-layer-zoom-select",
            options=[],
            value=None,
            placeholder="Select a historical map...",
            clearable=False,
        ),

        html.Button(
            "Zoom to layer",
            id="historical-layer-zoom-button",
            n_clicks=0,
            style={
                "marginTop": "8px",
                "width": "100%",
                "cursor": "pointer",
            },
        ),
    ],

    style={
        "position": "fixed",
        "top": "80px",
        "left": "20px",
        "zIndex": "1000",
        "width": "280px",
        "backgroundColor": "white",
        "padding": "12px",
        "borderRadius": "8px",
        "boxShadow": "0 2px 10px rgba(0,0,0,0.15)",
    },
    )


# =========================================================
# PAGE LAYOUT
# =========================================================

app.layout = html.Div(
    [
        create_layout(
            reference_map=reference_map,
            historical_map=historical_map,
        ),

        zoom_control,

        # Stores metadata needed for explicit layer navigation.
        dcc.Store(
            id="historical-layer-registry",
            data=[],
        ),
    ]
)


# =========================================================
# HELPERS
# =========================================================

def build_historical_layer_children(layer_registry):
    """
    Rebuild the complete LayersControl children.

    This is intentional. Instead of patching a Leaflet
    LayersControl repeatedly, we recreate its children from
    the registry. This keeps the Leaflet layer/control state
    consistent after multiple uploads.
    """

    children = [
        dl.BaseLayer(
            dl.TileLayer(
                url=HISTORICAL_BASE_URL,
                attribution="© OpenStreetMap contributors",
            ),
            name="OpenStreetMap",
            checked=True,
        )
    ]

    for item in layer_registry:

        raster_asset = RasterAsset(
            name=item["name"],
            original_path=Path(
                item.get("original_path", "")
            ),
            cog_path=Path(
                item["cog_path"]
            ),
            tile_url=item["tile_url"],
            bounds=item["bounds"],
            minzoom=item["minzoom"],
            maxzoom=item["maxzoom"],
        )

        children.append(
            create_historical_overlay(
                asset=raster_asset,
                filename=item["name"],
                opacity=item["opacity"],
            )
        )

    return children


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
# TIFF UPLOAD + LAYER NAVIGATION CALLBACK
# =========================================================

@app.callback(
    # -----------------------------------------------------
    # Raster outputs
    # -----------------------------------------------------

    Output(
        "reference-raster-layer",
        "url",
    ),

    Output(
        "reference-raster-layer",
        "maxNativeZoom",
    ),

    Output(
        "historical-layer-control",
        "children",
    ),

    # -----------------------------------------------------
    # Map view
    # -----------------------------------------------------

    Output(
        "reference-map",
        "center",
    ),

    Output(
        "reference-map",
        "zoom",
    ),

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
    # Historical layer registry + zoom selector
    # -----------------------------------------------------

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

    # =====================================================
    # INPUTS
    # =====================================================

    Input(
        "reference-upload",
        "contents",
    ),

    Input(
        "historical-upload",
        "contents",
    ),

    Input(
        "historical-layer-zoom-button",
        "n_clicks",
    ),

    # =====================================================
    # STATES
    # =====================================================

    State(
        "reference-upload",
        "filename",
    ),

    State(
        "historical-upload",
        "filename",
    ),

    State(
        "historical-layer-zoom-select",
        "value",
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
def handle_raster_upload(
    reference_contents,
    historical_contents,
    zoom_button_clicks,
    reference_filename,
    historical_filename,
    selected_layer_id,
    layer_registry,
    historical_opacity,
):

    triggered = ctx.triggered_id

    if layer_registry is None:
        layer_registry = []


    # =====================================================
    # ZOOM TO SELECTED HISTORICAL LAYER
    # =====================================================

    if triggered == "historical-layer-zoom-button":

        if not selected_layer_id:
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
                no_update,      # 10
                no_update,      # 11
                no_update,      # 12
            )

        selected_layer = next(
            (
                item
                for item in layer_registry
                if item.get("id") == selected_layer_id
            ),
            None,
        )

        if selected_layer is None:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                "Selected historical layer was not found.",
                no_update,
                no_update,
                no_update,
            )

        return (
            no_update,                         # 1
            no_update,                         # 2
            no_update,                         # 3

            selected_layer["center"],          # 4
            selected_layer["zoom"],            # 5

            selected_layer["center"],          # 6
            selected_layer["zoom"],            # 7

            no_update,                         # 8
            no_update,                         # 9

            no_update,                         # 10
            no_update,                         # 11
            no_update,                         # 12
        )


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

                no_update,
                no_update,
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
                f"Upload failed: {exc}",
                no_update,
                no_update,
                no_update,
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
            # Keep the current opacity.
            # -------------------------------------------------

            opacity = (
                historical_opacity / 100.0
                if historical_opacity is not None
                else 1.0
            )

            # -------------------------------------------------
            # Add new layer metadata to registry.
            # -------------------------------------------------

            layer_id = asset.cog_path.stem

            # Avoid duplicate registry entries.
            layer_registry = [
                item
                for item in layer_registry
                if item.get("id") != layer_id
            ]

            layer_registry.append(
                {
                    "id": layer_id,
                    "name": historical_filename,
                    "cog_path": str(
                        asset.cog_path
                    ),
                    "original_path": str(
                        asset.original_path
                    ),
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
            )

            # -------------------------------------------------
            # Rebuild ALL historical layers.
            #
            # This ensures the new raster is a real visible
            # Leaflet overlay, not only a newly patched control
            # entry.
            # -------------------------------------------------

            historical_children = (
                build_historical_layer_children(
                    layer_registry
                )
            )

            layer_options = [
                {
                    "label": item["name"],
                    "value": item["id"],
                }
                for item in layer_registry
            ]

            # -------------------------------------------------
            # IMPORTANT:
            #
            # Upload does not change the current view.
            # Use the explicit "Zoom to layer" button for that.
            # -------------------------------------------------

            return (
                no_update,                         # 1
                no_update,                         # 2

                historical_children,                # 3

                no_update,                         # 4
                no_update,                         # 5

                no_update,                         # 6
                no_update,                         # 7

                no_update,                         # 8
                f"Loaded: {historical_filename}",  # 9

                layer_registry,                    # 10
                layer_options,                     # 11
                layer_id,                           # 12
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
                no_update,
                no_update,
            )


    # =====================================================
    # FALLBACK
    # =====================================================

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
        no_update,
        no_update,
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

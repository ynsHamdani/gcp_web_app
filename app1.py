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

OSM_URL = (
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
# COMMON LAYER HELPERS
# =========================================================

def create_layers_control(control_id):
    """Create a LayersControl with OSM as the base layer."""

    osm = dl.BaseLayer(
        dl.TileLayer(
            url=OSM_URL,
            attribution="© OpenStreetMap contributors",
        ),
        name="OpenStreetMap",
        checked=True,
    )

    return [
        dl.LayersControl(
            id=control_id,
            children=[osm],
            position="topright",
        ),
        dl.FullScreenControl(
            position="bottomright",
        ),
        dl.ScaleControl(
            position="bottomleft",
        ),
    ]


def create_raster_overlay(asset, filename, layer_type, opacity=1.0):
    """Create one dynamic raster overlay."""

    return dl.Overlay(
        dl.TileLayer(
            id={
                "type": layer_type,
                "index": asset.cog_path.stem,
            },
            url=asset.tile_url,
            opacity=opacity,
            tileSize=256,
            maxZoom=24,
            zIndex=10,
        ),
        name=filename,
        checked=True,
    )


def build_layer_children(layer_registry, layer_type):
    """Rebuild all raster layers plus the OSM base layer."""

    children = [
        dl.BaseLayer(
            dl.TileLayer(
                url=OSM_URL,
                attribution="© OpenStreetMap contributors",
            ),
            name="OpenStreetMap",
            checked=True,
        )
    ]

    for item in layer_registry:

        asset = RasterAsset(
            name=item["name"],
            original_path=Path(item["original_path"]),
            cog_path=Path(item["cog_path"]),
            tile_url=item["tile_url"],
            bounds=item["bounds"],
            minzoom=item["minzoom"],
            maxzoom=item["maxzoom"],
        )

        children.append(
            create_raster_overlay(
                asset=asset,
                filename=item["name"],
                layer_type=layer_type,
                opacity=item["opacity"],
            )
        )

    return children


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

    children=create_layers_control(
        "reference-layer-control"
    ),

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

    children=create_layers_control(
        "historical-layer-control"
    ),

    style=MAP_STYLE,
)


# =========================================================
# REFERENCE ZOOM CONTROL
# =========================================================

reference_zoom_control = html.Div(
    [
        html.Div(
            "Zoom to reference layer",
            style={
                "fontWeight": "600",
                "marginBottom": "6px",
            },
        ),

        dcc.Dropdown(
            id="reference-layer-zoom-select",
            options=[],
            value=None,
            placeholder="Select a reference map...",
            clearable=False,
        ),

        html.Button(
            "Zoom to layer",
            id="reference-layer-zoom-button",
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
# HISTORICAL ZOOM CONTROL
# =========================================================

historical_zoom_control = html.Div(
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
        "left": "calc(50% + 20px)",
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

        reference_zoom_control,
        historical_zoom_control,

        dcc.Store(
            id="reference-layer-registry",
            data=[],
        ),

        dcc.Store(
            id="historical-layer-registry",
            data=[],
        ),
    ]
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
# REFERENCE TIFF UPLOAD
# =========================================================

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

    layer_registry = layer_registry or []

    original_path = None
    cog_path = None

    try:

        original_path = save_uploaded_tiff(
            contents,
            filename,
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
            name=filename,
            original_path=original_path,
            cog_path=cog_path,
            tile_url=tile_url,
            bounds=bounds,
            minzoom=minzoom,
            maxzoom=maxzoom,
        )

        opacity = (
            reference_opacity / 100.0
            if reference_opacity is not None
            else 1.0
        )

        layer_id = asset.cog_path.stem

        layer_registry = [
            item
            for item in layer_registry
            if item.get("id") != layer_id
        ]

        layer_registry.append(
            {
                "id": layer_id,
                "name": filename,
                "original_path": str(
                    asset.original_path
                ),
                "cog_path": str(
                    asset.cog_path
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

        children = build_layer_children(
            layer_registry,
            "reference-raster-layer",
        )

        options = [
            {
                "label": item["name"],
                "value": item["id"],
            }
            for item in layer_registry
        ]

        return (
            children,
            f"Loaded: {filename}",
            layer_registry,
            options,
            layer_id,
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
            f"Upload failed: {exc}",
            no_update,
            no_update,
            no_update,
        )


# =========================================================
# HISTORICAL TIFF UPLOAD
# =========================================================

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

    layer_registry = layer_registry or []

    original_path = None
    cog_path = None

    try:

        original_path = save_uploaded_tiff(
            contents,
            filename,
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
            name=filename,
            original_path=original_path,
            cog_path=cog_path,
            tile_url=tile_url,
            bounds=bounds,
            minzoom=minzoom,
            maxzoom=maxzoom,
        )

        opacity = (
            historical_opacity / 100.0
            if historical_opacity is not None
            else 1.0
        )

        layer_id = asset.cog_path.stem

        layer_registry = [
            item
            for item in layer_registry
            if item.get("id") != layer_id
        ]

        layer_registry.append(
            {
                "id": layer_id,
                "name": filename,
                "original_path": str(
                    asset.original_path
                ),
                "cog_path": str(
                    asset.cog_path
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

        children = build_layer_children(
            layer_registry,
            "historical-raster-layer",
        )

        options = [
            {
                "label": item["name"],
                "value": item["id"],
            }
            for item in layer_registry
        ]

        return (
            children,
            f"Loaded: {filename}",
            layer_registry,
            options,
            layer_id,
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
            f"Upload failed: {exc}",
            no_update,
            no_update,
            no_update,
        )


# =========================================================
# ZOOM TO SELECTED LAYER
# =========================================================
#
# One callback handles both maps' zoom buttons.
# This avoids duplicate Dash outputs while keeping the two
# maps linked: whichever layer is selected, both maps receive
# the same center/zoom.
# =========================================================

@app.callback(
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

    Input(
        "reference-layer-zoom-button",
        "n_clicks",
    ),
    Input(
        "historical-layer-zoom-button",
        "n_clicks",
    ),

    State(
        "reference-layer-zoom-select",
        "value",
    ),
    State(
        "historical-layer-zoom-select",
        "value",
    ),

    State(
        "reference-layer-registry",
        "data",
    ),
    State(
        "historical-layer-registry",
        "data",
    ),

    prevent_initial_call=True,
)
def zoom_to_selected_layer(
    reference_clicks,
    historical_clicks,
    selected_reference_id,
    selected_historical_id,
    reference_registry,
    historical_registry,
):

    triggered = ctx.triggered_id

    if triggered == "reference-layer-zoom-button":

        registry = reference_registry or []
        selected_id = selected_reference_id

    elif triggered == "historical-layer-zoom-button":

        registry = historical_registry or []
        selected_id = selected_historical_id

    else:

        return (
            no_update,
            no_update,
            no_update,
            no_update,
        )

    if not selected_id:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
        )

    selected_layer = next(
        (
            item
            for item in registry
            if item.get("id") == selected_id
        ),
        None,
    )

    if selected_layer is None:
        return (
            no_update,
            no_update,
            no_update,
            no_update,
        )

    center = selected_layer["center"]
    zoom = selected_layer["zoom"]

    return (
        center,
        zoom,
        center,
        zoom,
    )


# =========================================================
# REFERENCE OPACITY
# =========================================================

@app.callback(
    Output(
        {
            "type": "reference-raster-layer",
            "index": ALL,
        },
        "opacity",
    ),

    Input(
        "reference-opacity",
        "value",
    ),

    State(
        {
            "type": "reference-raster-layer",
            "index": ALL,
        },
        "id",
    ),

    prevent_initial_call=True,
)
def update_reference_opacity(
    value,
    layer_ids,
):

    opacity = value / 100.0

    return [
        opacity
        for _ in layer_ids
    ]


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

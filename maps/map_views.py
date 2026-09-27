from __future__ import annotations

from pathlib import Path

import dash_leaflet as dl
from dash_extensions.javascript import Namespace

from maps.raster import RasterAsset


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
# JAVASCRIPT SYNCHRONIZATION
# =========================================================

ns = Namespace(
    "gcpMapSync",
    "handlers",
)


# =========================================================
# LAYER HELPERS
# =========================================================

def create_layers_control(control_id: str):
    """Create the common Leaflet controls used by both maps."""

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


def create_raster_overlay(
    asset: RasterAsset,
    filename: str,
    layer_type: str,
    opacity: float = 1.0,
):
    """Create one dynamic raster overlay for a map."""

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


def raster_asset_from_registry(item: dict) -> RasterAsset:
    """Reconstruct a RasterAsset from a serialized layer-registry item."""

    return RasterAsset(
        name=item["name"],
        original_path=Path(item.get("original_path", "")),
        cog_path=Path(item["cog_path"]),
        tile_url=item["tile_url"],
        bounds=item["bounds"],
        minzoom=item["minzoom"],
        maxzoom=item["maxzoom"],
    )


def build_layer_children(
    layer_registry: list[dict] | None,
    layer_type: str,
):
    """Rebuild all OSM + uploaded raster layers from the registry."""

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

    for item in layer_registry or []:
        asset = raster_asset_from_registry(item)

        children.append(
            create_raster_overlay(
                asset=asset,
                filename=item["name"],
                layer_type=layer_type,
                opacity=item.get("opacity", 1.0),
            )
        )

    return children


# =========================================================
# MAP FACTORIES
# =========================================================

def create_reference_map():
    """Create the reference map with browser-side synchronization hooks."""

    return dl.Map(
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


def create_historical_map():
    """Create the historical map with the same synchronization hooks."""

    return dl.Map(
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

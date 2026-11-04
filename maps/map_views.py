from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import dash_leaflet as dl
from dash_extensions.javascript import Namespace

from config import CARTO_API_KEY, BASEMAP_PROVIDER_DEFAULT
from maps.raster import RasterAsset

INITIAL_CENTER = [56.15, 10.20]
INITIAL_ZOOM = 7
MAP_STYLE = {"width": "100%", "height": "100%"}

# The official OSM public-tile hostname has no subdomain prefix.
OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
CARTO_VOYAGER_URL = "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"
CARTO_ATTRIBUTION = (
    '© <a href="https://carto.com/attributions">CARTO</a> '
    '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
)

ns = Namespace("gcpMapSync", "handlers")


def resolve_basemap_provider(provider: str | None = None) -> str:
    """Resolve the selected provider; fall back safely if CARTO has no key."""
    if provider is None:
        try:
            from services.runtime_settings import get_basemap_provider
            provider = get_basemap_provider(BASEMAP_PROVIDER_DEFAULT)
        except Exception:
            provider = BASEMAP_PROVIDER_DEFAULT
    selected = str(provider or BASEMAP_PROVIDER_DEFAULT).strip().lower()
    if selected not in {"carto", "osm"}:
        selected = BASEMAP_PROVIDER_DEFAULT if BASEMAP_PROVIDER_DEFAULT in {"carto", "osm"} else "carto"
    if selected == "carto" and not CARTO_API_KEY:
        return "osm"
    return selected


def create_basemap(provider: str | None = None):
    """Return the base layer selected in Admin Configuration."""
    selected = resolve_basemap_provider(provider)
    if selected == "carto":
        url = f"{CARTO_VOYAGER_URL}?key={quote(CARTO_API_KEY, safe='')}"
        name, attribution = "CARTO Voyager", CARTO_ATTRIBUTION
    else:
        url, name, attribution = OSM_URL, "OpenStreetMap", OSM_ATTRIBUTION
    return dl.BaseLayer(
        dl.TileLayer(url=url, attribution=attribution, tileSize=256, maxZoom=20),
        name=name,
        checked=True,
    )


def create_layers_control(control_id: str, basemap_provider: str | None = None):
    """Create the common Leaflet controls used by both maps."""
    return [
        dl.LayersControl(id=control_id, children=[create_basemap(basemap_provider)], position="topright"),
        dl.FullScreenControl(position="bottomright"),
        dl.ScaleControl(position="bottomleft"),
    ]


def create_raster_overlay(asset: RasterAsset, filename: str, layer_type: str, opacity: float = 1.0):
    """Create one dynamic raster overlay for a map."""
    return dl.Overlay(
        dl.TileLayer(
            id={"type": layer_type, "index": asset.cog_path.stem},
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


def build_layer_children(layer_registry: list[dict] | None, layer_type: str, basemap_provider: str | None = None):
    """Build the selected basemap plus uploaded raster layers."""
    children = [create_basemap(basemap_provider)]
    for item in layer_registry or []:
        asset = raster_asset_from_registry(item)
        children.append(create_raster_overlay(asset, item["name"], layer_type, item.get("opacity", 1.0)))
    return children


def _create_map(map_id: str, control_id: str, gcp_layer_id: str, basemap_provider: str | None = None):
    reference = map_id == "reference-map"
    return dl.Map(
        id=map_id,
        center=INITIAL_CENTER,
        zoom=INITIAL_ZOOM,
        eventHandlers={
            "load": ns("registerReference" if reference else "registerHistorical"),
            "drag": ns("syncReference" if reference else "syncHistorical"),
            "dragend": ns("syncReference" if reference else "syncHistorical"),
            "zoom": ns("syncReference" if reference else "syncHistorical"),
            "zoomend": ns("syncReference" if reference else "syncHistorical"),
        },
        children=[*create_layers_control(control_id, basemap_provider), dl.LayerGroup(id=gcp_layer_id)],
        style=MAP_STYLE,
    )


def create_reference_map(basemap_provider: str | None = None):
    """Create the reference map with browser-side two-map synchronisation."""
    return _create_map("reference-map", "reference-layer-control", "reference-gcp-layer", basemap_provider)


def create_historical_map(basemap_provider: str | None = None):
    """Create the historical map with browser-side two-map synchronisation."""
    return _create_map("historical-map", "historical-layer-control", "historical-gcp-layer", basemap_provider)

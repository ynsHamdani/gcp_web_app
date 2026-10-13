from __future__ import annotations

"""Build admin map-layer registries from persistent metadata and live COG cache."""

from typing import Any

from config import TITILER_URL
from maps.map_views import build_layer_children
from maps.raster import (
    RasterAsset,
    calculate_fit_zoom,
    create_signed_raster_url,
    get_cached_raster_path,
    get_titiler_asset,
)


def build_admin_layer_state(layer_store) -> dict[str, Any]:
    """Return available overlays, historical filter options, and warnings.

    PostgreSQL layer metadata is authoritative for the layer list. Uploaded
    COGs are added to the map only if the temporary file still exists and
    TiTiler metadata can be retrieved. Missing files never remove GCP rows.
    """

    layers = layer_store.list()
    registries: dict[str, list[dict]] = {"reference": [], "historical": []}
    historical_options: list[dict[str, str]] = []
    unavailable: list[str] = []

    for layer in layers:
        kind = str(layer.get("layer_type", ""))
        source_type = layer.get("source_type")
        layer_id = str(layer.get("layer_id", ""))
        filename = str(layer.get("filename") or f"Layer {layer_id}")
        sha256 = layer.get("sha256")

        local_path = None
        if source_type == "uploaded" and kind in registries:
            local_path = get_cached_raster_path(kind, sha256)

        is_available = source_type == "basemap" or local_path is not None
        if kind == "historical":
            label = filename if is_available else f"{filename} (raster unavailable)"
            historical_options.append({"label": label, "value": layer_id})

        # OSM is already included as the basemap in the existing map factory.
        if source_type != "uploaded" or kind not in registries:
            continue
        if local_path is None:
            unavailable.append(filename)
            continue

        try:
            source_url = create_signed_raster_url(local_path)
            tile_url, bounds, minzoom, maxzoom = get_titiler_asset(
                source_url,
                TITILER_URL,
                local_path,
            )
            asset = RasterAsset(
                name=filename,
                original_path=local_path,
                cog_path=local_path,
                tile_url=tile_url,
                bounds=bounds,
                minzoom=minzoom,
                maxzoom=maxzoom,
            )
            registries[kind].append(
                {
                    "id": sha256,
                    "db_layer_id": layer_id,
                    "name": filename,
                    "original_path": "",
                    "cog_path": str(local_path),
                    "tile_url": asset.tile_url,
                    "bounds": asset.bounds,
                    "center": asset.center,
                    "zoom": calculate_fit_zoom(asset.bounds),
                    "minzoom": asset.minzoom,
                    "maxzoom": asset.maxzoom,
                    "opacity": 0.75,
                }
            )
        except Exception:
            # A locally present COG is not useful to the map if TiTiler cannot
            # read it. Keep the metadata/GCPs and flag the layer as unavailable.
            unavailable.append(f"{filename} (map service unavailable)")

    return {
        "reference_registry": registries["reference"],
        "historical_registry": registries["historical"],
        "historical_options": historical_options,
        "unavailable_layers": unavailable,
        "all_layers": layers,
    }


def install_registry_on_map(map_component, registry: list[dict], layer_kind: str):
    """Populate an existing synchronized map's layer control from the registry."""

    control_id = f"{layer_kind}-layer-control"
    for child in map_component.children or []:
        if getattr(child, "id", None) == control_id:
            overlays = build_layer_children(
                registry,
                f"{layer_kind}-raster-layer",
            )
            # Keep the basemap on and enable only one uploaded raster by default.
            # Other available overlays remain selectable in the layer control.
            raster_overlays = overlays[1:]
            for overlay in raster_overlays:
                overlay.checked = False
            if raster_overlays:
                raster_overlays[-1].checked = True
            child.children = overlays
            break
    return map_component

from __future__ import annotations

"""Build administrator layer options from PostgreSQL metadata and live COGs.

Only files that still exist in the shared COG cache and can be read by TiTiler
are offered as uploaded layers. The OpenStreetMap basemap is a special,
permanently available reference option and is already provided by the map.
"""

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
    """Return available registries, selector options, and availability warnings.

    ``historical_options`` intentionally contains unavailable historical
    metadata too, because old GCP records may still refer to an expired raster.
    The dedicated *Add a GCP* dropdown uses ``available_historical_options``
    and therefore never offers an unavailable raster.
    """

    layers = layer_store.list()
    registries: dict[str, list[dict]] = {"reference": [], "historical": []}
    historical_options: list[dict[str, str]] = []
    available_historical_options: list[dict[str, str]] = []
    reference_options: list[dict[str, str]] = []
    unavailable: list[str] = []
    basemap_reference_layer_id: str | None = None

    # Add the shared basemap to the reference selector. It is rendered by the
    # base layer in maps/map_views.py and does not require a COG overlay.
    for layer in layers:
        if (
            layer.get("layer_type") == "reference"
            and layer.get("source_type") == "basemap"
        ):
            layer_id = str(layer.get("layer_id", ""))
            filename = str(layer.get("filename") or "OpenStreetMap")
            if layer_id:
                basemap_reference_layer_id = basemap_reference_layer_id or layer_id
                reference_options.append(
                    {
                        "label": f"{filename} (basemap)",
                        "value": layer_id,
                    }
                )

    for layer in layers:
        kind = str(layer.get("layer_type", ""))
        source_type = str(layer.get("source_type") or "")
        layer_id = str(layer.get("layer_id", ""))
        filename = str(layer.get("filename") or f"Layer {layer_id}")
        sha256 = layer.get("sha256")

        if kind not in registries or source_type != "uploaded":
            if kind == "historical":
                historical_options.append(
                    {"label": f"{filename} (raster unavailable)", "value": layer_id}
                )
            continue

        local_path = get_cached_raster_path(kind, sha256)
        if local_path is None:
            unavailable.append(f"{kind.title()}: {filename} (raster unavailable)")
            if kind == "historical":
                historical_options.append(
                    {"label": f"{filename} (raster unavailable)", "value": layer_id}
                )
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
            entry = {
                "id": str(sha256),
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
            registries[kind].append(entry)

            option = {"label": filename, "value": layer_id}
            if kind == "reference":
                reference_options.append(option)
            else:
                historical_options.append(option)
                available_historical_options.append(option)
        except Exception as exc:
            unavailable.append(f"{kind.title()}: {filename} (map service unavailable: {exc})")
            if kind == "historical":
                historical_options.append(
                    {"label": f"{filename} (raster unavailable)", "value": layer_id}
                )

    # Keep selector labels and ordering predictable.
    reference_options.sort(key=lambda item: item["label"].casefold())
    historical_options.sort(key=lambda item: item["label"].casefold())
    available_historical_options.sort(key=lambda item: item["label"].casefold())

    return {
        "reference_registry": registries["reference"],
        "historical_registry": registries["historical"],
        "reference_options": reference_options,
        "historical_options": historical_options,
        "available_historical_options": available_historical_options,
        "unavailable_layers": unavailable,
        "basemap_reference_layer_id": basemap_reference_layer_id,
    }


def build_admin_selected_layer_control_children(
    registry: list[dict] | None,
    layer_kind: str,
    selected_db_layer_id: str | int | None,
):
    """Build a map control containing OSM and at most the selected COG overlay.

    Non-selected raster layers are deliberately omitted from the Leaflet map,
    not merely unchecked. They remain available in the searchable selectors.
    """

    if layer_kind not in {"reference", "historical"}:
        raise ValueError("layer_kind must be 'reference' or 'historical'.")

    selected = str(selected_db_layer_id) if selected_db_layer_id not in (None, "") else None
    chosen = [
        item
        for item in (registry or [])
        if selected is not None and str(item.get("db_layer_id")) == selected
    ]
    return build_layer_children(chosen, f"{layer_kind}-raster-layer")


def install_registry_on_map(
    map_component,
    registry: list[dict],
    layer_kind: str,
    selected_db_layer_ids: list[str] | set[str] | tuple[str, ...] | None = None,
):
    """Populate a map with only the selected uploaded COG layer."""

    control_id = f"{layer_kind}-layer-control"
    selected_ids = list(selected_db_layer_ids or [])
    selected_id = selected_ids[0] if selected_ids else None
    for child in map_component.children or []:
        if getattr(child, "id", None) == control_id:
            child.children = build_admin_selected_layer_control_children(
                registry,
                layer_kind,
                selected_id,
            )
            break
    return map_component

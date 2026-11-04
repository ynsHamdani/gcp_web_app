from __future__ import annotations

"""Small, explicit readiness rules for administrator GCP collection."""


def is_reference_available(layer_state: dict, db_layer_id) -> bool:
    if db_layer_id in (None, ""):
        return False
    basemap_id = layer_state.get("basemap_reference_layer_id")
    if basemap_id is not None and str(db_layer_id) == str(basemap_id):
        # A basemap is already mounted in the reference map and has no COG
        # cache entry. It is nevertheless a valid ground-reference support.
        return True
    return any(str(item.get("value")) == str(db_layer_id) for item in (layer_state.get("reference_options") or []))


def is_historical_available(layer_state: dict, db_layer_id) -> bool:
    if db_layer_id in (None, ""):
        return False
    return any(str(item.get("value")) == str(db_layer_id) for item in (layer_state.get("available_historical_options") or []))


def can_collect_gcp(layer_state: dict, loaded_selection: dict) -> bool:
    """A valid reference support plus an available historical raster are required."""
    return (
        is_reference_available(layer_state, loaded_selection.get("reference_db_layer_id"))
        and is_historical_available(layer_state, loaded_selection.get("historical_db_layer_id"))
    )

from __future__ import annotations

"""Admin GCP map rendering using Dash Leaflet 1.x GeoJSON clustering."""

_EMPTY_FEATURE_COLLECTION = {"type": "FeatureCollection", "features": []}


def build_admin_gcp_geojson(records: list[dict] | None, map_kind: str) -> dict:
    """Build a GeoJSON FeatureCollection for one synchronized map."""

    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")

    features = []
    for record in records or []:
        position = record.get(map_kind) or {}
        lat, lon = position.get("lat"), position.get("lon")
        if lat is None or lon is None:
            continue

        gcp_id = str(record.get("gcp_id") or "")
        contributor = str(record.get("student_username") or record.get("student_id") or "Unknown contributor")
        role = str(record.get("contributor_role") or "unknown")
        features.append(
            {
                "type": "Feature",
                "id": gcp_id,
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": {
                    "gcp_id": gcp_id,
                    "contributor": contributor,
                    "contributor_role": role,
                    "contributor_email": str(record.get("student_email") or ""),
                    "historical_layer": str(record.get("historical_layer_name") or "Unknown historical layer"),
                    "reference_layer": str(record.get("reference_layer_name") or "Unknown reference layer"),
                    "offset_m": float(record.get("offset_m") or 0.0),
                    "status": str(record.get("status") or "confirmed"),
                    "recorded_at": str(record.get("recorded_at") or ""),
                    "map_kind": map_kind,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def create_admin_gcp_geojson_layer(map_kind: str, records: list[dict] | None = None):
    """Create one stable clustered GeoJSON component."""

    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")

    import dash_leaflet as dl
    from dash_extensions.javascript import Namespace

    admin_gcp_js = Namespace("adminGcp", "handlers")
    return dl.GeoJSON(
        id=f"admin-{map_kind}-gcp-geojson",
        data=build_admin_gcp_geojson(records, map_kind),
        cluster=True,
        zoomToBoundsOnClick=True,
        superClusterOptions={"radius": 50, "maxZoom": 18, "minPoints": 2},
        pointToLayer=admin_gcp_js("pointToLayer"),
        onEachFeature=admin_gcp_js("onEachFeature"),
        hideout={"selected_gcp_id": None},
    )


def install_admin_gcp_layer(map_component, records: list[dict] | None, map_kind: str):
    """Install the confirmed GCP cluster and a separate pending-marker layer."""

    import dash_leaflet as dl

    group_id = f"{map_kind}-gcp-layer"
    for child in map_component.children or []:
        if getattr(child, "id", None) == group_id:
            child.children = [
                create_admin_gcp_geojson_layer(map_kind, records),
                dl.LayerGroup(id=f"admin-{map_kind}-pending-layer"),
            ]
            return map_component

    raise RuntimeError(f"Could not find {group_id!r} in the {map_kind} map component.")


def build_admin_gcp_row(record: dict) -> dict:
    """Flatten a joined GCP record for the administrator's table."""

    reference = record.get("reference") or {}
    historical = record.get("historical") or {}
    return {
        "gcp_id": record.get("gcp_id", ""),
        "student_id": record.get("student_id", ""),
        "student_username": record.get("student_username", ""),
        "contributor_role": record.get("contributor_role", ""),
        "student_email": record.get("student_email", ""),
        "historical_layer_id": record.get("historical_layer_id", ""),
        "historical_layer_name": record.get("historical_layer_name", ""),
        "reference_layer_id": record.get("reference_layer_id", ""),
        "reference_layer_name": record.get("reference_layer_name", ""),
        "reference_x": reference.get("x", ""),
        "reference_y": reference.get("y", ""),
        "reference_lon": reference.get("lon", ""),
        "reference_lat": reference.get("lat", ""),
        "historical_pixel": historical.get("pixel", ""),
        "historical_line": historical.get("line", ""),
        "historical_x": historical.get("x", ""),
        "historical_y": historical.get("y", ""),
        "historical_lon": historical.get("lon", ""),
        "historical_lat": historical.get("lat", ""),
        "offset_m": record.get("offset_m", ""),
        "reference_raster_available": "yes" if record.get("reference_raster_available") else "no",
        "historical_raster_available": "yes" if record.get("historical_raster_available") else "no",
        "status": record.get("status", "confirmed"),
        "recorded_at": record.get("recorded_at", ""),
    }


def build_admin_pending_markers(pending: dict | None, map_kind: str):
    """Create the fixed reference marker or draggable historical marker."""

    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")
    if not pending:
        return []

    import dash_leaflet as dl
    from dash_extensions.javascript import Namespace

    position = pending.get(map_kind) or {}
    if position.get("lat") is None or position.get("lon") is None:
        return []

    marker_kwargs = {
        "id": f"admin-pending-{map_kind}-gcp-marker",
        "position": [float(position["lat"]), float(position["lon"])],
        "draggable": map_kind == "historical",
        "bubblingMouseEvents": False,
        "opacity": 0.98,
        "title": (
            "Pending GCP — reference point"
            if map_kind == "reference"
            else "Pending GCP — drag to adjust historical position"
        ),
    }
    if map_kind == "historical":
        drag_namespace = Namespace("adminGcpCollection", "handlers")
        marker_kwargs["eventHandlers"] = {
            "dragend": drag_namespace("captureHistoricalDrag")
        }
    return [dl.Marker(**marker_kwargs)]

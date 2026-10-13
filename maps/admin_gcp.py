from __future__ import annotations

"""Clustered GCP rendering shared by the administrator's two maps."""

import dash_leaflet as dl


def build_admin_gcp_markers(records: list[dict] | None, map_kind: str):
    """Build clustered confirmed-GCP markers for reference or historical space."""

    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")

    markers = []
    for record in records or []:
        position = record.get(map_kind) or {}
        lat = position.get("lat")
        lon = position.get("lon")
        if lat is None or lon is None:
            continue

        gcp_id = str(record.get("gcp_id", "GCP"))
        owner = str(record.get("student_username") or record.get("student_id") or "unknown student")
        layer_name = str(record.get("historical_layer_name") or "unknown historical layer")
        markers.append(
            dl.Marker(
                position=[float(lat), float(lon)],
                title=f"{gcp_id} | student: {owner} | historical layer: {layer_name}",
                bubblingMouseEvents=False,
            )
        )

    return [
        dl.MarkerClusterGroup(
            children=markers,
            chunkedLoading=True,
            showCoverageOnHover=False,
            spiderfyOnMaxZoom=True,
        )
    ]


def build_admin_gcp_row(record: dict) -> dict:
    """Flatten one joined GCP record for the administrator's sortable table."""

    ref = record.get("reference") or {}
    hist = record.get("historical") or {}
    ref_available = bool(record.get("reference_raster_available", False))
    hist_available = bool(record.get("historical_raster_available", False))
    return {
        "gcp_id": record.get("gcp_id", ""),
        "student_id": record.get("student_id", ""),
        "student_username": record.get("student_username", ""),
        "student_email": record.get("student_email", ""),
        "historical_layer_id": record.get("historical_layer_id", ""),
        "historical_layer_name": record.get("historical_layer_name", ""),
        "reference_layer_id": record.get("reference_layer_id", ""),
        "reference_layer_name": record.get("reference_layer_name", ""),
        "reference_x": ref.get("x", ""),
        "reference_y": ref.get("y", ""),
        "reference_lon": ref.get("lon", ""),
        "reference_lat": ref.get("lat", ""),
        "historical_pixel": hist.get("pixel", ""),
        "historical_line": hist.get("line", ""),
        "historical_x": hist.get("x", ""),
        "historical_y": hist.get("y", ""),
        "historical_lon": hist.get("lon", ""),
        "historical_lat": hist.get("lat", ""),
        "offset_m": record.get("offset_m", ""),
        "status": record.get("status", ""),
        "reference_raster_available": "yes" if ref_available else "no",
        "historical_raster_available": "yes" if hist_available else "no",
        "recorded_at": record.get("recorded_at", ""),
    }

from __future__ import annotations

"""Domain logic for Ground Control Points.

Leaflet works with WGS84 latitude/longitude (EPSG:4326).  The authoritative
reference coordinates used by the project are stored in EPSG:25832.  For the
historical raster, the record also stores the raster-space position
(pixel/line) needed later by GDAL/QGIS for georeferencing.

This module contains data/geometry logic only.  It does not know about Dash,
JSON, PostgreSQL, or the UI.
"""

from datetime import datetime, timezone
from math import hypot
from typing import Any

from pyproj import Transformer

from config import GCP_CRS


_WGS84_TO_GCP = Transformer.from_crs(
    "EPSG:4326",
    GCP_CRS,
    always_xy=True,
)


# =========================================================
# COORDINATE HELPERS
# =========================================================


def normalize_position(position: Any) -> dict[str, float]:
    """Normalize Leaflet coordinates to ``{"lat": ..., "lon": ...}``.

    Accepted inputs:
    - [lat, lon]
    - {"lat": lat, "lng": lon}
    - {"lat": lat, "lon": lon}
    """

    if isinstance(position, dict):
        lat = position.get("lat")
        lon = position.get("lon", position.get("lng"))
    elif position is not None and len(position) == 2:
        lat = position[0]
        lon = position[1]
    else:
        raise ValueError("A valid [latitude, longitude] position is required.")

    if lat is None or lon is None:
        raise ValueError("A valid latitude/longitude position is required.")

    lat = float(lat)
    lon = float(lon)

    if not (-90.0 <= lat <= 90.0):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("Longitude must be between -180 and 180 degrees.")

    return {"lat": lat, "lon": lon}


def leaflet_to_gcp_position(position: Any) -> dict[str, float | str]:
    """Convert a Leaflet WGS84 position to EPSG:25832."""

    normalized = normalize_position(position)

    # always_xy=True means x=longitude and y=latitude for EPSG:4326.
    x, y = _WGS84_TO_GCP.transform(
        normalized["lon"],
        normalized["lat"],
    )

    return {
        "lat": normalized["lat"],
        "lon": normalized["lon"],
        "x": float(x),
        "y": float(y),
        "crs": GCP_CRS,
    }


def displacement_m(reference: dict, historical: dict) -> float:
    """Return the current historical/reference displacement in metres."""

    reference_x = float(reference["x"])
    reference_y = float(reference["y"])
    historical_x = float(historical["x"])
    historical_y = float(historical["y"])

    return float(
        hypot(
            historical_x - reference_x,
            historical_y - reference_y,
        )
    )


def utc_timestamp() -> str:
    """Return a timezone-aware UTC timestamp suitable for JSON/SQL."""

    return datetime.now(timezone.utc).isoformat()


# =========================================================
# GCP RECORD
# =========================================================


def build_gcp_record(
    *,
    reference_position: Any,
    historical_position: Any,
    historical_pixel: float,
    historical_line: float,
    student_id: str = "",
    reference_layer_id: str | None = None,
    historical_layer_id: str | None = None,
) -> dict:
    """Build a confirmed GCP record.

    The authoritative georeferencing relationship is:

        historical pixel/line -> reference X/Y (EPSG:25832)

    The historical X/Y and lat/lon are retained as quality-control metadata
    describing the historical raster's current georeferenced position.
    """

    reference = leaflet_to_gcp_position(reference_position)
    historical = leaflet_to_gcp_position(historical_position)

    return {
        "crs": GCP_CRS,
        "reference_layer_id": reference_layer_id,
        "historical_layer_id": historical_layer_id,
        "student_id": student_id,
        "reference": {
            "x": reference["x"],
            "y": reference["y"],
            "lon": reference["lon"],
            "lat": reference["lat"],
            "crs": GCP_CRS,
        },
        "historical": {
            "pixel": float(historical_pixel),
            "line": float(historical_line),
            "x": historical["x"],
            "y": historical["y"],
            "lon": historical["lon"],
            "lat": historical["lat"],
            "crs": GCP_CRS,
        },
        # This is the displacement in the historical map's CURRENT
        # georeferencing, before applying the new GCP transformation.
        "offset_m": round(displacement_m(reference, historical), 3),
        "status": "confirmed",
        "created_at": utc_timestamp(),
        "updated_at": utc_timestamp(),
    }


def gcp_table_row(record: dict) -> dict:
    """Convert one GCP record into the existing AG Grid row shape."""

    reference = record.get("reference", {})
    historical = record.get("historical", {})
    offset_m = float(record.get("offset_m", 0.0))

    student_id = record.get(
        "student_id",
        record.get("student", ""),
    )

    return {
        "gcp_id": record.get("gcp_id", ""),
        "feature_type": "Point",
        "reference": (
            f"{float(reference.get('x', 0.0)):.3f}, "
            f"{float(reference.get('y', 0.0)):.3f}"
        ),
        "historical": (
            f"{float(historical.get('x', 0.0)):.3f}, "
            f"{float(historical.get('y', 0.0)):.3f}"
        ),
        "offset": f"{offset_m:.2f} m",
        "student": student_id,
        "status": record.get("status", "confirmed"),
        "crs": record.get("crs", GCP_CRS),
    }

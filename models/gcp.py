from __future__ import annotations

"""Domain logic for Ground Control Points.

The application receives map clicks in WGS84 latitude/longitude because that
is the coordinate system used by Leaflet.  GCP coordinates are converted to
and stored in the project's authoritative projected CRS: EPSG:25832.

This module contains data/geometry logic only.  It does not know about Dash,
JSON, PostgreSQL, or the UI.
"""

from datetime import datetime, timezone
from math import hypot

from pyproj import Transformer

from config import GCP_CRS


_WGS84_TO_GCP = Transformer.from_crs(
    "EPSG:4326",
    GCP_CRS,
    always_xy=True,
)


def normalize_position(position) -> dict[str, float]:
    """Normalize a Leaflet [lat, lon] position."""

    if not position or len(position) != 2:
        raise ValueError("A valid [latitude, longitude] position is required.")

    lat = float(position[0])
    lon = float(position[1])

    if not (-90.0 <= lat <= 90.0):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("Longitude must be between -180 and 180 degrees.")

    return {"lat": lat, "lon": lon}


def leaflet_to_gcp_position(position) -> dict[str, float | str]:
    """Convert a Leaflet WGS84 [lat, lon] position to EPSG:25832."""

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
    """Return planar displacement in metres using stored EPSG:25832 X/Y."""

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


def build_gcp_record(
    *,
    reference_position,
    historical_position,
    student: str = "",
    reference_layer_id: str | None = None,
    historical_layer_id: str | None = None,
) -> dict:
    """Build a confirmed GCP record with authoritative EPSG:25832 X/Y."""

    reference = leaflet_to_gcp_position(reference_position)
    historical = leaflet_to_gcp_position(historical_position)

    return {
        "crs": GCP_CRS,
        "reference": reference,
        "historical": historical,
        "offset_m": round(displacement_m(reference, historical), 3),
        "status": "confirmed",
        "timestamp": utc_timestamp(),
        "student": student,
        "reference_layer_id": reference_layer_id,
        "historical_layer_id": historical_layer_id,
    }


def gcp_table_row(record: dict) -> dict:
    """Convert one domain record into the existing AG Grid row shape.

    The table now displays the authoritative projected coordinates (metres)
    rather than latitude/longitude.
    """

    reference = record["reference"]
    historical = record["historical"]
    offset_m = float(record.get("offset_m", 0.0))

    return {
        "gcp_id": record.get("gcp_id", ""),
        "feature_type": "Point",
        "reference": f"{float(reference['x']):.3f}, {float(reference['y']):.3f}",
        "historical": f"{float(historical['x']):.3f}, {float(historical['y']):.3f}",
        "offset": f"{offset_m:.2f} m",
        "student": record.get("student", ""),
        "status": record.get("status", "confirmed"),
        "crs": record.get("crs", GCP_CRS),
    }

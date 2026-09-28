from __future__ import annotations

"""Domain model for Ground Control Points.

Leaflet positions are handled as WGS84 latitude/longitude. The authoritative
ground coordinates stored for the GCP use EPSG:25832. Historical raster
pixel/line coordinates are the source coordinates required by GDAL-style
georeferencing.
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
    """Normalize Leaflet coordinates to {'lat': ..., 'lon': ...}."""

    if isinstance(position, dict):
        lat = position.get("lat")
        lon = position.get("lon", position.get("lng"))
        if lat is None or lon is None:
            raise ValueError("A valid latitude/longitude position is required.")
    else:
        if not position or len(position) != 2:
            raise ValueError("A valid [latitude, longitude] position is required.")
        lat = position[0]
        lon = position[1]

    lat = float(lat)
    lon = float(lon)

    if not (-90.0 <= lat <= 90.0):
        raise ValueError("Latitude must be between -90 and 90 degrees.")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("Longitude must be between -180 and 180 degrees.")

    return {"lat": lat, "lon": lon}


def leaflet_to_gcp_position(position) -> dict[str, float | str]:
    """Convert a Leaflet WGS84 position to EPSG:25832."""

    normalized = normalize_position(position)

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
    """Return planar displacement in metres."""

    return float(
        hypot(
            float(historical["x"]) - float(reference["x"]),
            float(historical["y"]) - float(reference["y"]),
        )
    )


def utc_timestamp() -> str:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def build_gcp_record(
    *,
    reference_position,
    historical_position,
    historical_pixel: float,
    historical_line: float,
    student_id: str = "",
    reference_layer_id: str | None = None,
    historical_layer_id: str | None = None,
) -> dict:
    """Build the final persisted GCP record."""

    reference = leaflet_to_gcp_position(reference_position)
    historical = leaflet_to_gcp_position(historical_position)

    return {
        "gcp_id": None,
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
        "offset_m": round(displacement_m(reference, historical), 3),
        "status": "confirmed",
        "recorded_at": utc_timestamp(),
    }


def gcp_table_row(record: dict) -> dict:
    """Convert one GCP record into the AG Grid row shape."""

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
        "recorded_at": record.get("recorded_at", ""),
    }

from __future__ import annotations

"""Pure GeoJSON conversion for the student's own confirmed GCP records."""

import math


def build_student_gcp_geojson(records: list[dict] | None, map_kind: str) -> dict:
    """Build a minimal FeatureCollection for one student map.

    The student map only needs the GCP identifier and point geometry. Keeping
    the payload intentionally small makes clustered rendering inexpensive and
    avoids exposing unrelated record metadata in the map layer.
    """
    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")

    features: list[dict] = []
    for record in records or []:
        position = record.get(map_kind) or {}
        try:
            lat = float(position["lat"])
            lon = float(position["lon"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue

        gcp_id = str(record.get("gcp_id") or "").strip()
        if not gcp_id:
            continue

        features.append(
            {
                "type": "Feature",
                "id": gcp_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "properties": {"gcp_id": gcp_id},
            }
        )

    return {"type": "FeatureCollection", "features": features}

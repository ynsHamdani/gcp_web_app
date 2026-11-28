from __future__ import annotations

"""Map-side rendering of student GCP markers.

Confirmed records use the same GeoJSON clustering approach as the Admin maps.
The single pending GCP remains a separate Leaflet marker so the historical
position can still be dragged independently of the cluster layer.
"""

import dash_leaflet as dl
from dash_extensions.javascript import Namespace

from maps.student_gcp import build_student_gcp_geojson

_ns = Namespace("gcpMapGcp", "handlers")
_student_ns = Namespace("studentGcp", "handlers")


def _marker_position(position: dict) -> list[float]:
    """Return a Leaflet [latitude, longitude] position."""
    return [float(position["lat"]), float(position["lon"])]


def build_gcp_layer_children(
    records: list[dict] | None,
    pending: dict | None,
    selected_gcp_id: str | None,
    map_kind: str,
    collection_active: bool = False,
):
    """Build clustered confirmed GCPs and a separate editable pending point.

    While collection is active, the confirmed-GCP GeoJSON layer is rendered
    but made non-interactive and cluster-click zooming is disabled. Clicks
    therefore reach the reference map, while the pending historical marker
    remains independently draggable. In browse mode, normal cluster behavior
    is restored.
    """
    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")

    collection_active = bool(collection_active)
    children = [
        dl.GeoJSON(
            id=f"student-{map_kind}-gcp-geojson",
            data=build_student_gcp_geojson(records, map_kind),
            cluster=True,
            zoomToBoundsOnClick=not collection_active,
            superClusterOptions={"radius": 50, "maxZoom": 18, "minPoints": 2},
            pointToLayer=_student_ns("pointToLayer"),
            onEachFeature=_student_ns("onEachFeature"),
            hideout={"selected_gcp_id": str(selected_gcp_id) if selected_gcp_id else None},
            interactive=not collection_active,
            bubblingMouseEvents=True,
        )
    ]

    # The pending GCP is intentionally never inserted into the cluster. This
    # preserves the fixed reference point and draggable historical point.
    if pending:
        position = pending.get(map_kind) or {}
        if position.get("lat") is not None and position.get("lon") is not None:
            marker_kwargs = dict(
                id=f"pending-{map_kind}-gcp-marker",
                position=_marker_position(position),
                draggable=(map_kind == "historical"),
                bubblingMouseEvents=False,
                opacity=0.95,
                title=(
                    "Pending GCP — reference point"
                    if map_kind == "reference"
                    else "Pending GCP — drag to adjust historical position"
                ),
            )
            if map_kind == "historical":
                marker_kwargs["eventHandlers"] = {
                    "dragend": _ns("captureHistoricalDrag"),
                }
            children.append(dl.Marker(**marker_kwargs))

    return children

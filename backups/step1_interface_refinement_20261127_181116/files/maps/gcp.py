from __future__ import annotations

"""Map-side rendering of GCP markers.

No persistence logic lives here. The callback layer provides records/pending
state and this module only turns that state into Dash Leaflet components.

Compatible with dash-leaflet 1.1.3: Marker does not support ``popup=`` as a
keyword argument, so marker metadata uses ``title=`` instead.
"""

import dash_leaflet as dl
from dash_extensions.javascript import Namespace


_ns = Namespace("gcpMapGcp", "handlers")


def _marker_position(position: dict) -> list[float]:
    """Return a Leaflet [latitude, longitude] position."""

    return [float(position["lat"]), float(position["lon"])]


def build_gcp_layer_children(
    records: list[dict] | None,
    pending: dict | None,
    selected_gcp_id: str | None,
    map_kind: str,
):
    """Build confirmed and pending GCP graphics for one map.

    ``map_kind`` must be either ``reference`` or ``historical``.
    Historical pending markers are draggable; reference pending markers are
    fixed so the student can move only the historical point.
    """

    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")

    children = []
    records = records or []

    # -----------------------------------------------------
    # Confirmed GCPs
    # -----------------------------------------------------
    for record in records:
        position = record[map_kind]
        gcp_id = record["gcp_id"]

        children.append(
            dl.Marker(
                id={
                    "type": f"{map_kind}-gcp-marker",
                    "gcp_id": gcp_id,
                },
                position=_marker_position(position),
                draggable=False,
                bubblingMouseEvents=False,
                title=(
                    f"{gcp_id} | "
                    f"{position['lat']:.6f}, {position['lon']:.6f}"
                ),
            )
        )

        # Highlight the selected GCP without relying on Marker popup support.
        if gcp_id == selected_gcp_id:
            children.append(
                dl.CircleMarker(
                    center=_marker_position(position),
                    radius=10,
                    weight=3,
                    fillOpacity=0.15,
                    interactive=False,
                )
            )

    # -----------------------------------------------------
    # One pending GCP can be edited at a time
    # -----------------------------------------------------
    if pending:
        position = pending[map_kind]

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

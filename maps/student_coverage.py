from __future__ import annotations

import dash_leaflet as dl
from dash_extensions.javascript import Namespace

_EMPTY_FC = {"type": "FeatureCollection", "features": []}
_STUDENT_NS = Namespace("studentCoverage", "handlers")


def install_student_coverage_overlays(map_component, layers: list[dict], map_kind: str):
    """Add a separate coverage-only layer control; raster controls stay untouched."""
    if map_kind not in {"reference", "historical"}:
        raise ValueError("map_kind must be 'reference' or 'historical'.")
    overlays = []
    for item in layers or []:
        layer_id = str(item["coverage_layer_id"])
        label = f"Assigned: {item['layer_name']} · v{item['version']} ({int(item['assigned_feature_count']):,})"
        overlays.append(dl.Overlay(
            dl.GeoJSON(
                id={"type": "student-coverage-geojson", "map": map_kind, "layer_id": layer_id},
                data=_EMPTY_FC,
                pane="student-coverage-pane",
                style=_STUDENT_NS("polygonStyle"),
                onEachFeature=_STUDENT_NS("onEachFeature"),
                interactive=True,
                # Feature clicks must reach the map only while GCP collection
                # is active. student_coverage_map.js stops propagation in
                # browse mode and deliberately allows it in collection mode.
                bubblingMouseEvents=True,
            ),
            name=label,
            checked=True,
        ))
    if overlays:
        map_component.children = [
            *(map_component.children or []),
            # Keep work-area polygons below GCP markers in Leaflet's pane order.
            dl.Pane(name="student-coverage-pane", style={"zIndex": 350}),
            dl.LayersControl(
                id=f"{map_kind}-coverage-layer-control",
                position="bottomright",
                collapsed=True,
                children=overlays,
            ),
        ]
    return map_component

from __future__ import annotations

from dash import ALL, Input, Output, State
from flask import abort
from flask_login import current_user

from services.coverage_assignment import leaflet_bounds_to_dict

_EMPTY_FC = {"type": "FeatureCollection", "features": []}


def _require_student_id() -> int:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "student":
        abort(403)
    return int(current_user.get_id())


def register_student_coverage_callbacks(app, assignment_store) -> None:
    """Viewport-load each assigned version independently on both synchronized maps."""

    @app.callback(
        Output({"type": "student-coverage-geojson", "map": "reference", "layer_id": ALL}, "data"),
        Output("student-reference-coverage-status", "children"),
        Input("reference-map", "bounds"), Input("reference-map", "zoom"),
        State("student-coverage-layer-registry", "data"),
        prevent_initial_call=False,
    )
    def update_reference_assigned_polygons(bounds, zoom, registry):
        student_id = _require_student_id()
        if not registry:
            return [], ""
        try:
            normalized = leaflet_bounds_to_dict(bounds)
            output, shown, too_many = [], 0, False
            for item in registry:
                result = assignment_store.query_student_geojson(
                    student_id=student_id, layer_id=item["coverage_layer_id"],
                    bounds=normalized, zoom=zoom or 10,
                )
                output.append(result["geojson"])
                shown += result["feature_count_in_view"]
                too_many = too_many or result["too_many_features"]
            status = ("Zoom in to display assigned polygons in this map view; too many assigned features are visible."
                      if too_many else f"Showing {shown:,} assigned polygon(s) in the reference map view.")
            return output, status
        except ValueError as exc:
            return [_EMPTY_FC for _ in registry], str(exc)
        except Exception as exc:
            return [_EMPTY_FC for _ in registry], f"Assigned coverage could not be loaded: {exc}"

    @app.callback(
        Output({"type": "student-coverage-geojson", "map": "historical", "layer_id": ALL}, "data"),
        Output("student-historical-coverage-status", "children"),
        Input("historical-map", "bounds"), Input("historical-map", "zoom"),
        State("student-coverage-layer-registry", "data"),
        prevent_initial_call=False,
    )
    def update_historical_assigned_polygons(bounds, zoom, registry):
        student_id = _require_student_id()
        if not registry:
            return [], ""
        try:
            normalized = leaflet_bounds_to_dict(bounds)
            output, shown, too_many = [], 0, False
            for item in registry:
                result = assignment_store.query_student_geojson(
                    student_id=student_id, layer_id=item["coverage_layer_id"],
                    bounds=normalized, zoom=zoom or 10,
                )
                output.append(result["geojson"])
                shown += result["feature_count_in_view"]
                too_many = too_many or result["too_many_features"]
            status = ("Zoom in to display assigned polygons in this map view; too many assigned features are visible."
                      if too_many else f"Showing {shown:,} assigned polygon(s) in the historical map view.")
            return output, status
        except ValueError as exc:
            return [_EMPTY_FC for _ in registry], str(exc)
        except Exception as exc:
            return [_EMPTY_FC for _ in registry], f"Assigned coverage could not be loaded: {exc}"

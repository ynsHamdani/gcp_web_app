from __future__ import annotations

import json

from dash import Input, Output, State, ctx, html, no_update
from flask import abort
from flask_login import current_user


def _require_admin() -> int:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)
    return int(current_user.get_id())


def _alert(message: str, *, success: bool):
    level = "success" if success else "error"
    colors = (
        {"background": "#f0fdf4", "border": "1px solid #bbf7d0", "color": "#166534"}
        if success else
        {"background": "#fef2f2", "border": "1px solid #fecaca", "color": "#7f1d1d"}
    )
    return html.Div(
        [
            html.Span(message, style={"flex": "1 1 auto"}),
            html.Button("×", className="coverage-alert-close", type="button", **{"aria-label": "Dismiss notification"}),
        ],
        className="coverage-dismissible-alert",
        style={**colors, "padding": "9px 11px", "borderRadius": "7px", "lineHeight": "1.45"},
    )


def _feature_from_click(click_data: dict | None) -> int | None:
    if not isinstance(click_data, dict):
        return None
    feature = click_data.get("feature") or {}
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties") or {}
    raw = props.get("coverage_feature_id", feature.get("id"))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def register_coverage_assignment_callbacks(app, assignment_store, auth_store) -> None:
    """Manage one selected polygon's one-to-many student assignments."""

    @app.callback(
        Output("coverage-selected-feature", "data"),
        Output("coverage-selected-feature-label", "children"),
        Output("coverage-assignment-students", "value"),
        Output("coverage-polygons", "hideout"),
        Input("coverage-polygons", "clickData"),
        Input("coverage-analysis-layer", "value"),
        State("coverage-selected-feature", "data"),
        prevent_initial_call=True,
    )
    def select_polygon(click_data, layer_id, previous_selection):
        _require_admin()
        if ctx.triggered_id == "coverage-analysis-layer":
            return None, "Coverage version changed. Select a polygon to manage its assignments.", [], {"selected_feature_id": None}
        feature_id = _feature_from_click(click_data)
        if feature_id is None or not layer_id:
            return no_update, no_update, no_update, no_update
        feature = assignment_store.get_feature_for_assignment(feature_id, int(layer_id))
        if feature is None:
            return None, "The clicked polygon is not available in the selected active coverage version. Refresh the map and select it again.", [], {"selected_feature_id": None}
        attrs = feature.get("attributes") or {}
        label = feature.get("feature_label") or feature.get("source_feature_key") or f"Feature {feature_id}"
        summary = (
            f"Selected: {feature['layer_name']} · v{feature['version']} · {label} "
            f"(feature ID {feature_id}). The dropdown shows the current assignments."
        )
        return (
            {"coverage_feature_id": feature_id, "coverage_layer_id": int(layer_id)},
            summary,
            [str(value) for value in feature["assigned_student_ids"]],
            {"selected_feature_id": str(feature_id)},
        )

    @app.callback(
        Output("coverage-assignment-save", "disabled"),
        Input("coverage-selected-feature", "data"),
        Input("coverage-assignment-saving", "data"),
    )
    def set_assignment_save_enabled(selection, saving):
        return not bool(selection and selection.get("coverage_feature_id") and not saving)

    @app.callback(
        Output("coverage-assignment-save-status", "children"),
        Input("coverage-assignment-save", "n_clicks"),
        State("coverage-selected-feature", "data"),
        State("coverage-assignment-students", "value"),
        prevent_initial_call=True,
        running=[
            (Output("coverage-assignment-saving", "data"), True, False),
            (Output("coverage-assignment-loading", "style"),
             {"display": "flex", "alignItems": "center", "gap": "9px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "10px"},
             {"display": "none", "alignItems": "center", "gap": "9px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "10px"}),
        ],
    )
    def save_polygon_assignments(n_clicks, selection, student_values):
        if not n_clicks:
            return no_update
        actor_id = _require_admin()
        if not selection:
            return _alert("Select a polygon on the map first.", success=False)
        feature_id = int(selection["coverage_feature_id"])
        layer_id = int(selection["coverage_layer_id"])
        try:
            selected_ids = assignment_store.replace_feature_assignments(
                feature_id=feature_id,
                layer_id=layer_id,
                student_ids=student_values or [],
                assigned_by=actor_id,
            )
            try:
                auth_store.log_admin_action(
                    actor_id,
                    "coverage_feature_students_assigned",
                    "coverage_feature",
                    feature_id,
                    {"coverage_layer_id": layer_id, "student_ids": selected_ids},
                )
            except Exception:
                # Audit logging must not roll back or make a valid assignment
                # appear to have failed after the database transaction commits.
                pass
            if not selected_ids:
                return _alert(f"All student assignments were removed from polygon {feature_id}.", success=True)
            return _alert(f"Saved {len(selected_ids)} student assignment(s) for polygon {feature_id}.", success=True)
        except Exception as exc:
            return _alert(f"Assignments were not saved: {exc}", success=False)

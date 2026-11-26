from __future__ import annotations

from dash import Input, Output, State, html, no_update
from flask import abort
from flask_login import current_user

from auth.permissions import is_admin_role


def _require_admin() -> int:
    if not current_user.is_authenticated or not is_admin_role(getattr(current_user, "role", None)):
        abort(403)
    return int(current_user.get_id())


def _alert(message: str, *, success: bool):
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


def register_coverage_assignment_callbacks(app, assignment_store, auth_store) -> None:
    """Manage one selected polygon's one-to-many student assignments.

    The map writes the selected polygon ID into a dedicated dcc.Store from its
    Leaflet click handler. This callback only reads that stable selection and
    loads the current student assignments; it does not update GeoJSON props.
    Keeping map rendering out of this callback prevents popup/highlight loss
    when the assignment dropdown is used.
    """

    @app.callback(
        Output("coverage-selected-feature-label", "children"),
        Output("coverage-assignment-students", "value"),
        Output("coverage-assignment-objective", "value"),
        Output("coverage-assignment-instructions", "value"),
        Input("coverage-selected-feature", "data"),
        prevent_initial_call=True,
    )
    def load_selected_polygon_assignments(selection):
        _require_admin()
        if not selection:
            return "No polygon selected. Click a polygon on the map to manage its assignments.", [], "", ""

        try:
            feature_id = int(selection.get("coverage_feature_id"))
            layer_id = int(selection.get("coverage_layer_id"))
            if feature_id <= 0 or layer_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return "The selected polygon reference is invalid. Select it again on the map.", [], "", ""

        feature = assignment_store.get_feature_for_assignment(feature_id, layer_id)
        if feature is None:
            return (
                "The selected polygon is no longer available in this active coverage version. "
                "Refresh the map and select it again.",
                [], "", "",
            )

        label = feature.get("feature_label") or feature.get("source_feature_key") or f"Feature {feature_id}"
        summary = (
            f"Selected: {feature['layer_name']} · v{feature['version']} · {label} "
            f"(feature ID {feature_id}). The dropdown shows the current assignments."
        )
        return (
            summary,
            [str(value) for value in feature.get("assigned_student_ids", [])],
            str(feature.get("objective") or ""),
            str(feature.get("instructions") or ""),
        )

    # Clear the persistent selection when the administrator changes coverage
    # versions. The map data itself is refreshed by the existing map callback.
    @app.callback(
        Output("coverage-selected-feature", "data"),
        Input("coverage-analysis-layer", "value"),
        prevent_initial_call=True,
    )
    def clear_selection_on_layer_change(_layer_id):
        _require_admin()
        return None

    @app.callback(
        Output("coverage-assignment-save", "disabled"),
        Input("coverage-selected-feature", "data"),
        Input("coverage-assignment-saving", "data"),
        Input("coverage-analysis-layer", "value"),
    )
    def set_assignment_save_enabled(selection, saving, active_layer_id):
        try:
            valid_selection = (
                isinstance(selection, dict)
                and int(selection.get("coverage_feature_id")) > 0
                and int(selection.get("coverage_layer_id")) > 0
                and str(selection.get("coverage_layer_id")) == str(active_layer_id)
            )
        except (TypeError, ValueError):
            valid_selection = False
        return not (valid_selection and not bool(saving))

    @app.callback(
        Output("coverage-assignment-save-status", "children"),
        Input("coverage-assignment-save", "n_clicks"),
        State("coverage-selected-feature", "data"),
        State("coverage-assignment-students", "value"),
        State("coverage-assignment-objective", "value"),
        State("coverage-assignment-instructions", "value"),
        State("coverage-analysis-layer", "value"),
        prevent_initial_call=True,
        running=[
            (Output("coverage-assignment-saving", "data"), True, False),
            (Output("coverage-assignment-loading", "style"),
             {"display": "flex", "alignItems": "center", "gap": "9px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "10px"},
             {"display": "none", "alignItems": "center", "gap": "9px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "10px"}),
        ],
    )
    def save_polygon_assignments(n_clicks, selection, student_values, objective, instructions, active_layer_id):
        if not n_clicks:
            return no_update
        actor_id = _require_admin()
        if not selection:
            return _alert("Select a polygon on the map first.", success=False)
        try:
            feature_id = int(selection["coverage_feature_id"])
            layer_id = int(selection["coverage_layer_id"])
            if str(layer_id) != str(active_layer_id):
                return _alert("The selected polygon belongs to a different coverage version. Select a polygon from the current version and try again.", success=False)
            selected_ids = assignment_store.replace_feature_assignments(
                feature_id=feature_id,
                layer_id=layer_id,
                student_ids=student_values or [],
                assigned_by=actor_id,
                objective=objective or "",
                instructions=instructions or "",
            )
            try:
                auth_store.log_admin_action(
                    actor_id,
                    "coverage_feature_students_assigned",
                    "coverage_feature",
                    feature_id,
                    {
                        "coverage_layer_id": layer_id,
                        "student_ids": selected_ids,
                        "objective_length": len(str(objective or "").strip()),
                        "instructions_length": len(str(instructions or "").strip()),
                    },
                )
            except Exception:
                # Preserve the committed assignment while making the audit
                # failure visible in the application log for follow-up.
                import logging
                logging.getLogger(__name__).exception(
                    "Could not write coverage assignment audit record"
                )
            if not selected_ids:
                return _alert(f"All student assignments were removed from polygon {feature_id}. The task text was saved for possible future allocation.", success=True)
            return _alert(f"Saved the task and {len(selected_ids)} student assignment(s) for polygon {feature_id}.", success=True)
        except Exception as exc:
            return _alert(f"Assignments were not saved: {exc}", success=False)

from __future__ import annotations

"""Student-side semantic context modal and atomic GCP creation."""

from dash import Input, Output, State, no_update
from flask import abort
from flask_login import current_user

from callbacks.gcp import (
    _historical_pixel_line,
    _resolve_layer_ids,
)
from models.gcp import build_gcp_record


def _require_student() -> int:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "student":
        abort(403)
    return int(current_user.get_id())


def register_gcp_context_callbacks(app, gcp_store, context_store) -> None:
    """Register modal visibility and student GCP save callbacks.

    The existing GCP workflow owns pending point creation/cancellation. This
    module only opens the context modal and commits a complete record when the
    student explicitly presses Save.
    """

    @app.callback(
        Output("gcp-context-modal", "style"),
        Output("gcp-context-status", "children"),
        Input("confirm-gcp-button", "n_clicks"),
        Input("close-gcp-context-button", "n_clicks"),
        Input("cancel-gcp-button", "n_clicks"),
        State("gcp-pending", "data"),
        prevent_initial_call=True,
    )
    def show_context_modal(confirm_clicks, close_clicks, cancel_clicks, pending):
        del confirm_clicks, close_clicks, cancel_clicks
        from dash import ctx

        if ctx.triggered_id == "confirm-gcp-button":
            if not pending:
                return no_update, "There is no pending GCP to annotate."
            try:
                categories = context_store.list_active()
            except Exception as exc:
                return {"display": "flex"}, f"Could not load context categories: {exc}"
            if not categories:
                return {"display": "flex"}, "No active context categories are configured. Contact an administrator."
            return {"display": "flex"}, "Select the geographical context for this GCP."
        return {"display": "none"}, ""

    @app.callback(
        Output("gcp-pending", "data", allow_duplicate=True),
        Output("gcp-records", "data", allow_duplicate=True),
        Output("gcp-status", "children", allow_duplicate=True),
        Output("gcp-context-modal", "style", allow_duplicate=True),
        Output("gcp-context-status", "children", allow_duplicate=True),
        Output("gcp-context-category", "value"),
        Output("gcp-context-remark", "value"),
        Output("confirm-gcp-button", "disabled", allow_duplicate=True),
        Output("cancel-gcp-button", "disabled", allow_duplicate=True),
        Input("save-gcp-context-button", "n_clicks"),
        State("gcp-pending", "data"),
        State("gcp-context-category", "value"),
        State("gcp-context-remark", "value"),
        State("reference-layer-registry", "data"),
        State("historical-layer-registry", "data"),
        prevent_initial_call=True,
    )
    def save_contextual_gcp(
        n_clicks, pending, category_id, remark, reference_registry, historical_registry
    ):
        if not n_clicks:
            return (no_update,) * 9
        student_id = _require_student()
        if not pending:
            return (
                no_update, no_update, "No pending GCP is available to save.",
                {"display": "none"}, no_update, None, None, True, True,
            )
        try:
            if category_id in (None, ""):
                raise ValueError("Choose a context category before saving the GCP.")
            context_store.validate_selectable(int(category_id))
            reference_db_id, historical_db_id = _resolve_layer_ids(
                pending, reference_registry, historical_registry
            )
            pixel, line = _historical_pixel_line(
                historical_registry,
                pending.get("historical_layer_id"),
                pending["historical"],
            )
            record = build_gcp_record(
                reference_position=[pending["reference"]["lat"], pending["reference"]["lon"]],
                historical_position=[pending["historical"]["lat"], pending["historical"]["lon"]],
                historical_pixel=pixel,
                historical_line=line,
                student_id=str(student_id),
                reference_layer_id=str(reference_db_id),
                historical_layer_id=str(historical_db_id),
            )
            # One INSERT statement persists geometry and context atomically.
            saved = gcp_store.create(
                record,
                context_category_id=int(category_id),
                context_remark=remark,
            )
            records = gcp_store.list_for_student(student_id)
            return (
                None,
                records,
                f"Confirmed {saved['gcp_id']} — {saved.get('context_category_label', 'context recorded')} — offset: {float(saved['offset_m']):.2f} m.",
                {"display": "none"}, "", None, None, True, True,
            )
        except Exception as exc:
            # Keep the pending point and modal intact so the user can correct
            # the form or retry. No partial GCP row is created.
            return (
                no_update, no_update, no_update,
                {"display": "flex"}, str(exc),
                no_update, no_update, False, False,
            )

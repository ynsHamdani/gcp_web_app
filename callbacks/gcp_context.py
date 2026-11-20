from __future__ import annotations

"""Student-side semantic context modal and atomic GCP creation."""

from dash import Input, Output, State, ctx, no_update
from flask import abort
from flask_login import current_user

from callbacks.gcp import _historical_pixel_line, _resolve_layer_ids
from models.gcp import build_gcp_record
from ui.gcp_context_components import student_context_modal_style


def _require_student() -> int:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "student":
        abort(403)
    return int(current_user.get_id())


def register_gcp_context_callbacks(app, gcp_store, context_store) -> None:
    """Open/discard the blocking dialog and save geometry + context atomically."""

    @app.callback(
        Output("gcp-context-modal", "style"),
        Output("gcp-context-status", "children"),
        Output("gcp-pending", "data", allow_duplicate=True),
        Output("gcp-status", "children", allow_duplicate=True),
        Output("gcp-context-category", "value", allow_duplicate=True),
        Output("gcp-context-remark", "value", allow_duplicate=True),
        Output("confirm-gcp-button", "disabled", allow_duplicate=True),
        Output("cancel-gcp-button", "disabled", allow_duplicate=True),
        Input("confirm-gcp-button", "n_clicks"),
        Input("discard-gcp-context-button", "n_clicks"),
        Input("cancel-gcp-button", "n_clicks"),
        State("gcp-pending", "data"),
        prevent_initial_call=True,
    )
    def manage_context_modal(confirm_clicks, discard_clicks, cancel_clicks, pending):
        del confirm_clicks, discard_clicks, cancel_clicks
        _require_student()
        if ctx.triggered_id == "confirm-gcp-button":
            if not pending:
                return (no_update, "There is no pending GCP to annotate.", *(no_update,) * 6)
            try:
                categories = context_store.list_active()
            except Exception as exc:
                return (student_context_modal_style(True), f"Could not load context categories: {exc}", *(no_update,) * 6)
            if not categories:
                return (
                    student_context_modal_style(True),
                    "No active context categories are configured. Please contact an administrator.",
                    *(no_update,) * 6,
                )
            return (
                student_context_modal_style(True),
                "Select the geographical context for this GCP.",
                *(no_update,) * 6,
            )

        if ctx.triggered_id == "discard-gcp-context-button":
            if not pending:
                return (
                    student_context_modal_style(False), "", no_update, no_update,
                    None, "", True, True,
                )
            return (
                student_context_modal_style(False),
                "",
                None,
                "Pending GCP discarded. No record was saved.",
                None,
                "",
                True,
                True,
            )

        # The ordinary page-level Cancel button also closes the modal. The
        # existing GCP workflow owns clearing the pending point in that path.
        return (student_context_modal_style(False), "", *(no_update,) * 6)

    @app.callback(
        Output("gcp-pending", "data", allow_duplicate=True),
        Output("gcp-records", "data", allow_duplicate=True),
        Output("gcp-status", "children", allow_duplicate=True),
        Output("gcp-context-modal", "style", allow_duplicate=True),
        Output("gcp-context-status", "children", allow_duplicate=True),
        Output("gcp-context-category", "value", allow_duplicate=True),
        Output("gcp-context-remark", "value", allow_duplicate=True),
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
                no_update,
                no_update,
                "No pending GCP is available to save.",
                student_context_modal_style(False),
                "",
                None,
                "",
                True,
                True,
            )
        try:
            if category_id in (None, ""):
                raise ValueError("GCP context is required. Select a category before saving; your GCP has not been saved.")
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
            # Geometry and semantic context are persisted by one SQL INSERT.
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
                student_context_modal_style(False),
                "",
                None,
                "",
                True,
                True,
            )
        except Exception as exc:
            # Keep the pending point and the dialog open so the user can fix
            # the required annotation or retry. No partial GCP row is created.
            return (
                no_update,
                no_update,
                no_update,
                student_context_modal_style(True),
                str(exc),
                no_update,
                no_update,
                False,
                False,
            )

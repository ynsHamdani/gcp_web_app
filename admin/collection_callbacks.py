from __future__ import annotations

from dash import Input, Output, State, ctx, no_update
from flask import abort
from flask_login import current_user

from callbacks.gcp import (
    _extract_click_position,
    _extract_drag_position,
    _format_pending_status,
    _historical_pixel_line,
    _pending_position,
)
from maps.admin_gcp import build_admin_pending_markers
from models.gcp import build_gcp_record


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _registry_entry_by_db_id(registry: list[dict], db_layer_id):
    if db_layer_id in (None, ""):
        return None
    target = str(db_layer_id)
    return next(
        (item for item in (registry or []) if str(item.get("db_layer_id")) == target),
        None,
    )


def _reference_is_available(layer_state: dict, db_layer_id) -> bool:
    return any(
        str(option.get("value")) == str(db_layer_id)
        for option in (layer_state.get("reference_options") or [])
    )


def _selected_entries(layer_state: dict, loaded_selection: dict):
    reference_db_id = loaded_selection.get("reference_db_layer_id")
    historical_db_id = loaded_selection.get("historical_db_layer_id")
    reference_registry = layer_state.get("reference_registry") or []
    historical_registry = layer_state.get("historical_registry") or []

    if not _reference_is_available(layer_state, reference_db_id):
        raise ValueError("Load an available reference layer before collecting GCPs.")

    historical_entry = _registry_entry_by_db_id(historical_registry, historical_db_id)
    if historical_entry is None:
        raise ValueError("Load an available historical raster before collecting GCPs.")

    reference_entry = _registry_entry_by_db_id(reference_registry, reference_db_id)
    # Uploaded layers use their SHA-based UI identity in the student workflow.
    # Basemap layers have no registry entry, so their numeric database ID is used.
    reference_ui_id = reference_entry.get("id") if reference_entry else str(reference_db_id)
    historical_ui_id = str(historical_entry["id"])

    return {
        "reference_db_id": str(reference_db_id),
        "historical_db_id": str(historical_db_id),
        "reference_ui_id": reference_ui_id,
        "historical_ui_id": historical_ui_id,
        "historical_entry": historical_entry,
        "reference_registry": reference_registry,
        "historical_registry": historical_registry,
    }


def register_admin_collection_callbacks(app, gcp_store):
    """Expose the existing click/drag/confirm GCP workflow to administrators."""

    @app.callback(
        Output("admin-gcp-pending", "data"),
        Output("admin-gcp-collection-status", "children"),
        Output("admin-confirm-gcp-button", "disabled"),
        Output("admin-cancel-gcp-button", "disabled"),
        Output("admin-gcp-drag-event", "clear_data"),
        Output("admin-gcp-collection-active", "data"),
        Output("admin-add-gcp-button", "children"),
        Output("admin-gcp-collection-revision", "data"),
        Input("admin-add-gcp-button", "n_clicks"),
        Input("reference-map", "clickData"),
        Input("admin-gcp-drag-event", "data"),
        Input("admin-confirm-gcp-button", "n_clicks"),
        Input("admin-cancel-gcp-button", "n_clicks"),
        Input("admin-loaded-layer-selection", "data"),
        State("admin-gcp-pending", "data"),
        State("admin-gcp-collection-active", "data"),
        State("admin-selection-layer-state", "data"),
        State("admin-gcp-collection-revision", "data"),
        prevent_initial_call=True,
    )
    def manage_admin_gcp_collection(
        add_clicks,
        reference_click,
        drag_event,
        confirm_clicks,
        cancel_clicks,
        loaded_selection_input,
        pending,
        collection_active,
        layer_state,
        revision,
    ):
        del add_clicks, confirm_clicks, cancel_clicks
        _require_admin()
        triggered = ctx.triggered_id
        pending = pending or None
        collection_active = bool(collection_active)
        layer_state = layer_state or {}
        loaded_selection = loaded_selection_input or {}
        revision = int(revision or 0)

        def unchanged(status=no_update, confirm=no_update, cancel=no_update, pending_value=no_update, active=None, button=no_update, revision_value=no_update):
            return (
                pending_value,
                status,
                confirm,
                cancel,
                True,
                collection_active if active is None else active,
                button if button is not no_update else ("Stop GCP" if collection_active else "Add GCP"),
                revision_value,
            )

        # A changed layer selection invalidates any pending point that was
        # created against the previous map pair.
        if triggered == "admin-loaded-layer-selection":
            if pending:
                return (
                    None,
                    "Loaded layers changed; the pending GCP was cancelled. Start a new point on the reference map.",
                    True,
                    True,
                    True,
                    False,
                    "Add GCP",
                    revision,
                )
            try:
                _selected_entries(layer_state, loaded_selection_input or {})
                status = "Reference and historical layers are loaded. Click Add GCP to start collecting."
            except Exception:
                status = "Choose and load an available reference and historical layer to enable GCP collection."
            return (
                None,
                status,
                True,
                True,
                True,
                False,
                "Add GCP",
                revision,
            )

        # Start/stop collection. The two selected layers must be present and
        # live in the current admin layer registry before placement is enabled.
        if triggered == "admin-add-gcp-button":
            if collection_active:
                return unchanged(
                    status=("Collection paused. Confirm or cancel the pending point, or click Add GCP to resume." if pending else "GCP collection paused."),
                    confirm=not bool(pending),
                    cancel=not bool(pending),
                    active=False,
                    button="Add GCP",
                )
            try:
                _selected_entries(layer_state, loaded_selection)
            except Exception as exc:
                return unchanged(status=str(exc), active=False, button="Add GCP")
            return unchanged(
                status="GCP collection active — click a point on the reference map.",
                confirm=not bool(pending),
                cancel=not bool(pending),
                active=True,
                button="Stop GCP",
            )

        # First click on the reference map creates a provisional matching pair.
        if triggered == "reference-map":
            if not collection_active:
                return unchanged(status="GCP collection is inactive. Click Add GCP first.")
            if pending:
                return unchanged(
                    status="A GCP is already pending. Adjust the historical marker, then confirm or cancel it.",
                    confirm=False,
                    cancel=False,
                )
            click_position = _extract_click_position(reference_click)
            if click_position is None:
                return unchanged(status="Could not read the clicked map position.")
            try:
                selected = _selected_entries(layer_state, loaded_selection)
                reference_position = _pending_position(click_position)
                # Validate that the reference point falls within the selected
                # historical image before presenting it as a pending GCP.
                _historical_pixel_line(
                    selected["historical_registry"],
                    selected["historical_ui_id"],
                    reference_position,
                )
            except Exception as exc:
                return unchanged(status=f"Cannot create GCP here: {exc}")

            pending = {
                "reference": reference_position,
                "historical": dict(reference_position),
                "reference_layer_id": selected["reference_ui_id"],
                "historical_layer_id": selected["historical_ui_id"],
                "reference_db_layer_id": selected["reference_db_id"],
                "historical_db_layer_id": selected["historical_db_id"],
            }
            return unchanged(
                pending_value=pending,
                status=_format_pending_status(pending),
                confirm=False,
                cancel=False,
            )

        # Dragging the historical marker moves only the historical endpoint.
        if triggered == "admin-gcp-drag-event":
            drag_position = _extract_drag_position(drag_event)
            if not pending or drag_position is None:
                return unchanged()
            try:
                selected = _selected_entries(layer_state, loaded_selection)
                historical_position = _pending_position(drag_position)
                _historical_pixel_line(
                    selected["historical_registry"],
                    pending.get("historical_layer_id"),
                    historical_position,
                )
            except Exception as exc:
                return unchanged(
                    status=f"Invalid historical position: {exc}",
                    confirm=False,
                    cancel=False,
                )
            pending = dict(pending)
            pending["historical"] = historical_position
            return unchanged(pending_value=pending, status=_format_pending_status(pending), confirm=False, cancel=False)

        # Persist the point under the logged-in administrator's own user ID.
        if triggered == "admin-confirm-gcp-button":
            if not pending:
                return unchanged(status="There is no pending GCP to confirm.", confirm=True, cancel=True)
            try:
                selected = _selected_entries(layer_state, loaded_selection)
                if (
                    str(pending.get("reference_db_layer_id")) != selected["reference_db_id"]
                    or str(pending.get("historical_db_layer_id")) != selected["historical_db_id"]
                ):
                    raise ValueError("The selected layers changed while this GCP was pending. Cancel it and start again.")

                pixel, line = _historical_pixel_line(
                    selected["historical_registry"],
                    selected["historical_ui_id"],
                    pending["historical"],
                )
                record = build_gcp_record(
                    reference_position=[pending["reference"]["lat"], pending["reference"]["lon"]],
                    historical_position=[pending["historical"]["lat"], pending["historical"]["lon"]],
                    historical_pixel=pixel,
                    historical_line=line,
                    student_id=str(int(current_user.get_id())),
                    reference_layer_id=selected["reference_db_id"],
                    historical_layer_id=selected["historical_db_id"],
                )
                saved = gcp_store.create(record)
            except Exception as exc:
                return unchanged(
                    status=f"Could not confirm GCP: {exc}",
                    confirm=False,
                    cancel=False,
                )

            message = f"Confirmed {saved['gcp_id']} — offset: {float(saved['offset_m']):.2f} m."
            if collection_active:
                message += " Click the reference map to place the next GCP."
            return (
                None,
                message,
                True,
                True,
                True,
                collection_active,
                "Stop GCP" if collection_active else "Add GCP",
                revision + 1,
            )

        # Cancel only discards the uncommitted point; no database row exists yet.
        if triggered == "admin-cancel-gcp-button":
            message = "Pending GCP cancelled. "
            message += "Click the reference map to place another point." if collection_active else "Collection is inactive."
            return unchanged(
                pending_value=None,
                status=message,
                confirm=True,
                cancel=True,
            )

        return unchanged()

    @app.callback(
        Output("admin-reference-pending-layer", "children"),
        Output("admin-historical-pending-layer", "children"),
        Input("admin-gcp-pending", "data"),
    )
    def render_admin_pending_gcp(pending):
        return (
            build_admin_pending_markers(pending, "reference"),
            build_admin_pending_markers(pending, "historical"),
        )

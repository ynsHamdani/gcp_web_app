from __future__ import annotations

from pathlib import Path

import rasterio
from dash import ALL, Input, Output, State, ctx, no_update
from dash import html
from flask import abort
from flask_login import current_user

from maps.raster import prepare_uploaded_raster
from services.admin_layers import (
    build_admin_layer_state,
    build_admin_selected_layer_control_children,
)
from services.admin_layer_summary import summarize_unavailable_layers


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _option_exists(options: list[dict], value) -> bool:
    return value not in (None, "") and any(
        str(item.get("value")) == str(value) for item in (options or [])
    )


def _first_option(options: list[dict]):
    return options[0].get("value") if options else None


def _registry_entry(registry: list[dict], db_layer_id):
    return next(
        (item for item in (registry or []) if str(item.get("db_layer_id")) == str(db_layer_id)),
        None,
    ) if db_layer_id not in (None, "") else None


def _layer_name(state: dict, kind: str, db_layer_id) -> str:
    if db_layer_id in (None, ""):
        return "not selected"
    options = state.get("reference_options", []) if kind == "reference" else state.get("available_historical_options", [])
    selected = next((item for item in options if str(item.get("value")) == str(db_layer_id)), None)
    return selected.get("label", str(db_layer_id)) if selected else str(db_layer_id)


def _apply_opacity(registry: list[dict], db_layer_id, percent) -> list[dict]:
    opacity = max(0.0, min(1.0, float(percent if percent is not None else 75) / 100.0))
    result = []
    for original in registry or []:
        item = dict(original)
        if db_layer_id not in (None, "") and str(item.get("db_layer_id")) == str(db_layer_id):
            item["opacity"] = opacity
        result.append(item)
    return result


def _layer_control(state: dict, kind: str, db_layer_id):
    return build_admin_selected_layer_control_children(
        state.get(f"{kind}_registry", []),
        kind,
        db_layer_id,
    )


def _layer_indicator(selected_id, loaded_id, active_id) -> str:
    if selected_id in (None, ""):
        return "No layer selected."
    if str(loaded_id or "") != str(selected_id):
        return "Selected · not loaded"
    if str(active_id or "") == str(selected_id):
        return "Loaded · active for GCP collection"
    return "Loaded · press Zoom to activate for GCP collection"


def _availability_details(unavailable: list[str]):
    summary = summarize_unavailable_layers(unavailable)
    if summary["total"] == 0:
        return html.Span(
            "All registered uploaded rasters are currently available.",
            style={"fontSize": "11px", "color": "#166534"},
        )

    grouped = []
    for kind, title in (("reference", "Reference layers"), ("historical", "Historical layers"), ("other", "Other")):
        names = summary["groups"].get(kind, [])
        if not names:
            continue
        grouped.append(
            html.Div(
                [
                    html.Strong(f"{title} ({len(names)})", style={"fontSize": "11px"}),
                    html.Ul(
                        [html.Li(name, style={"marginBottom": "2px"}) for name in names],
                        style={"margin": "4px 0 8px 18px", "padding": "0", "fontSize": "11px", "color": "#7c2d12"},
                    ),
                ]
            )
        )

    return html.Details(
        [
            html.Summary(
                f"{summary['total']} unavailable raster(s) · {summary['reference']} reference · {summary['historical']} historical",
                style={"cursor": "pointer", "fontSize": "11px", "fontWeight": "600", "color": "#92400e"},
            ),
            html.Div(grouped, style={"padding": "6px 4px 0"}),
        ],
        open=False,
        style={"marginTop": "7px"},
    )


def _upload_one(contents: str, filename: str, kind: str, layer_store) -> tuple[str, str]:
    """Run the same temporary COG pipeline used by student uploads."""

    if not contents or not filename:
        raise ValueError("Choose a GeoTIFF file first.")

    safe_filename = Path(str(filename).replace("\\", "/")).name
    if Path(safe_filename).suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError("Only .tif and .tiff GeoTIFF files are accepted.")

    asset = prepare_uploaded_raster(
        contents=contents,
        filename=safe_filename,
        raster_kind=kind,
    )

    with rasterio.open(asset.cog_path) as src:
        if src.crs is None:
            raise ValueError(f"{safe_filename} has no coordinate reference system.")
        layer_record = {
            "layer_type": kind,
            "source_type": "uploaded",
            "filename": safe_filename,
            "sha256": Path(asset.cog_path).stem,
            "crs": src.crs.to_string(),
            "extent": [
                float(src.bounds.left),
                float(src.bounds.bottom),
                float(src.bounds.right),
                float(src.bounds.top),
            ],
            "width": int(src.width),
            "height": int(src.height),
        }

    db_layer = layer_store.upsert(layer_record)
    return str(db_layer["layer_id"]), safe_filename


def _normalise_loaded_selection(value: dict | None) -> dict:
    value = value or {}
    return {
        "reference_loaded_db_layer_id": value.get("reference_loaded_db_layer_id") or value.get("reference_db_layer_id"),
        "historical_loaded_db_layer_id": value.get("historical_loaded_db_layer_id") or value.get("historical_db_layer_id"),
        "reference_db_layer_id": value.get("reference_db_layer_id"),
        "historical_db_layer_id": value.get("historical_db_layer_id"),
    }


def _preserve_valid_selection(state: dict, loaded: dict) -> dict:
    ref_loaded = loaded.get("reference_loaded_db_layer_id")
    hist_loaded = loaded.get("historical_loaded_db_layer_id")
    if not _option_exists(state.get("reference_options", []), ref_loaded):
        ref_loaded = None
    if not _option_exists(state.get("available_historical_options", []), hist_loaded):
        hist_loaded = None

    ref_active = loaded.get("reference_db_layer_id")
    hist_active = loaded.get("historical_db_layer_id")
    if ref_active is None or str(ref_active) != str(ref_loaded):
        ref_active = None
    if hist_active is None or str(hist_active) != str(hist_loaded):
        hist_active = None
    return {
        "reference_loaded_db_layer_id": str(ref_loaded) if ref_loaded is not None else None,
        "historical_loaded_db_layer_id": str(hist_loaded) if hist_loaded is not None else None,
        "reference_db_layer_id": str(ref_active) if ref_active is not None else None,
        "historical_db_layer_id": str(hist_active) if hist_active is not None else None,
    }


def register_admin_layer_callbacks(app, layer_store):
    """Own layer selection/loading, explicit activation/zoom, and upload actions."""

    @app.callback(
        Output("reference-layer-control", "children"),
        Output("historical-layer-control", "children"),
        Output("admin-selection-layer-state", "data"),
        Output("admin-layer-state", "data"),
        Output("admin-reference-existing-select", "options"),
        Output("admin-reference-existing-select", "value"),
        Output("admin-historical-existing-select", "options"),
        Output("admin-historical-existing-select", "value"),
        Output("admin-loaded-layer-selection", "data"),
        Output("admin-layer-load-status", "children"),
        Output("admin-upload-status", "children"),
        Output("admin-add-gcp-button", "disabled"),
        Output("admin-unavailable-layer-note", "children"),
        Output("admin-layer-viewport-request", "data"),
        Output("admin-reference-layer-indicator", "children"),
        Output("admin-historical-layer-indicator", "children"),
        Input("admin-load-reference-layer", "n_clicks"),
        Input("admin-load-historical-layer", "n_clicks"),
        Input("admin-zoom-reference-layer", "n_clicks"),
        Input("admin-zoom-historical-layer", "n_clicks"),
        Input("admin-upload-layers", "n_clicks"),
        Input("admin-refresh", "n_clicks"),
        Input("admin-reference-existing-select", "value"),
        Input("admin-historical-existing-select", "value"),
        State("admin-reference-upload", "contents"),
        State("admin-reference-upload", "filename"),
        State("admin-historical-upload", "contents"),
        State("admin-historical-upload", "filename"),
        State("admin-loaded-layer-selection", "data"),
        State("admin-selection-layer-state", "data"),
        State("admin-reference-opacity", "value"),
        State("admin-historical-opacity", "value"),
        prevent_initial_call=True,
    )
    def manage_admin_layers(
        load_reference_clicks,
        load_historical_clicks,
        zoom_reference_clicks,
        zoom_historical_clicks,
        upload_clicks,
        refresh_clicks,
        reference_choice,
        historical_choice,
        reference_contents,
        reference_filename,
        historical_contents,
        historical_filename,
        loaded_selection_input,
        selection_layer_state,
        reference_opacity,
        historical_opacity,
    ):
        del load_reference_clicks, load_historical_clicks, zoom_reference_clicks, zoom_historical_clicks, upload_clicks, refresh_clicks
        _require_admin()
        triggered = ctx.triggered_id
        loaded = _normalise_loaded_selection(loaded_selection_input)
        upload_messages: list[str] = []
        uploaded_ids: dict[str, str] = {}

        if triggered == "admin-upload-layers":
            selected_files = [
                ("reference", reference_contents, reference_filename),
                ("historical", historical_contents, historical_filename),
            ]
            if not any(contents and filename for _kind, contents, filename in selected_files):
                return (
                    no_update, no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update,
                    "Choose a reference GeoTIFF, a historical GeoTIFF, or both before uploading.",
                    no_update, no_update, no_update, no_update, no_update, no_update,
                )
            for kind, contents, filename in selected_files:
                if not contents or not filename:
                    continue
                try:
                    db_id, safe_name = _upload_one(contents, filename, kind, layer_store)
                    uploaded_ids[kind] = db_id
                    upload_messages.append(f"{kind.title()} uploaded and registered: {safe_name}")
                except Exception as exc:
                    upload_messages.append(f"{kind.title()} upload failed: {exc}")

        try:
            if triggered == "admin-refresh" or triggered == "admin-upload-layers":
                state = build_admin_layer_state(layer_store)
            else:
                # Use the per-browser serialized registry for load/zoom. These
                # actions must not re-query TiTiler or regenerate unrelated URLs.
                state = dict(selection_layer_state or {})
                if not state:
                    state = build_admin_layer_state(layer_store)
        except Exception as exc:
            return (
                no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                f"Could not inspect registered layers: {exc}",
                "; ".join(upload_messages) if upload_messages else no_update,
                no_update, no_update, no_update, no_update, no_update,
            )

        # A per-request state is passed from the layout store; no registry data
        # is copied into a global cache between administrators/sessions.
        reference_options = state.get("reference_options", [])
        historical_options = state.get("available_historical_options", [])

        selected_ref = uploaded_ids.get("reference") or reference_choice
        selected_hist = uploaded_ids.get("historical") or historical_choice
        if triggered == "admin-refresh":
            selected_ref = selected_ref if _option_exists(reference_options, selected_ref) else _first_option(reference_options)
            selected_hist = selected_hist if _option_exists(historical_options, selected_hist) else _first_option(historical_options)
        else:
            if not _option_exists(reference_options, selected_ref):
                selected_ref = _first_option(reference_options)
            if not _option_exists(historical_options, selected_hist):
                selected_hist = _first_option(historical_options)

        next_loaded = _preserve_valid_selection(state, loaded)
        # The active layer must always match the current selector value. This
        # also invalidates an old active layer immediately after an upload has
        # selected a newly registered raster, before any follow-up callback.
        if str(selected_ref or "") != str(next_loaded.get("reference_db_layer_id") or ""):
            next_loaded["reference_db_layer_id"] = None
        if str(selected_hist or "") != str(next_loaded.get("historical_db_layer_id") or ""):
            next_loaded["historical_db_layer_id"] = None
        viewport_request = no_update
        layer_status = ""
        upload_status = "; ".join(upload_messages) if upload_messages else no_update

        # A selector change alone never changes what is on the map. Only the
        # matching Load action replaces that map's sole raster overlay.
        if triggered == "admin-load-reference-layer":
            if not _option_exists(reference_options, reference_choice):
                layer_status = "Choose an available reference layer first."
            else:
                changed = str(next_loaded["reference_loaded_db_layer_id"] or "") != str(reference_choice)
                next_loaded["reference_loaded_db_layer_id"] = str(reference_choice)
                if changed:
                    next_loaded["reference_db_layer_id"] = None
                layer_status = f"Loaded reference: {_layer_name(state, 'reference', reference_choice)}. Press Zoom to activate it for GCP collection."
        elif triggered == "admin-load-historical-layer":
            if not _option_exists(historical_options, historical_choice):
                layer_status = "Choose an available historical layer first."
            else:
                changed = str(next_loaded["historical_loaded_db_layer_id"] or "") != str(historical_choice)
                next_loaded["historical_loaded_db_layer_id"] = str(historical_choice)
                if changed:
                    next_loaded["historical_db_layer_id"] = None
                layer_status = f"Loaded historical: {_layer_name(state, 'historical', historical_choice)}. Press Zoom to activate it for GCP collection."
        elif triggered == "admin-reference-existing-select":
            if str(reference_choice or "") != str(next_loaded.get("reference_db_layer_id") or ""):
                next_loaded["reference_db_layer_id"] = None
            layer_status = "Reference selection changed. Load and Zoom the selected layer before collecting GCPs."
        elif triggered == "admin-historical-existing-select":
            if str(historical_choice or "") != str(next_loaded.get("historical_db_layer_id") or ""):
                next_loaded["historical_db_layer_id"] = None
            layer_status = "Historical selection changed. Load and Zoom the selected layer before collecting GCPs."
        elif triggered in {"admin-zoom-reference-layer", "admin-zoom-historical-layer"}:
            kind = "reference" if triggered == "admin-zoom-reference-layer" else "historical"
            choice = reference_choice if kind == "reference" else historical_choice
            loaded_id = next_loaded[f"{kind}_loaded_db_layer_id"]
            options = reference_options if kind == "reference" else historical_options
            if not _option_exists(options, choice):
                layer_status = f"Choose an available {kind} layer first."
            elif str(choice) != str(loaded_id):
                layer_status = f"Load the selected {kind} layer before zooming to it."
            else:
                next_loaded[f"{kind}_db_layer_id"] = str(choice)
                send_viewport = True
                if kind == "reference" and str(choice) == str(state.get("basemap_reference_layer_id")):
                    # A basemap has no finite geographic footprint. Activate it
                    # without changing the user's current synchronized extent.
                    send_viewport = False
                    layer_status = "OpenStreetMap is active as the reference layer; current map view is unchanged."
                else:
                    registry = state.get(f"{kind}_registry", [])
                    entry = _registry_entry(registry, choice)
                    if not entry:
                        next_loaded[f"{kind}_db_layer_id"] = None
                        layer_status = f"The selected {kind} raster is no longer available. Refresh the layer list."
                    else:
                        center = entry.get("center")
                        zoom = entry.get("zoom")
                        if not center or zoom is None:
                            next_loaded[f"{kind}_db_layer_id"] = None
                            layer_status = f"The selected {kind} raster has no usable geographic extent."
                        else:
                            layer_status = f"{_layer_name(state, kind, choice)} is active for GCP collection. Both maps will zoom to its extent."
                if next_loaded.get(f"{kind}_db_layer_id") and send_viewport:
                    viewport_request = {
                        "center": [float(center[0]), float(center[1])],
                        "zoom": int(zoom),
                        "request_id": f"{kind}:{choice}:{ctx.triggered[0]['value'] if ctx.triggered else ''}",
                    }
        elif triggered == "admin-upload-layers":
            if uploaded_ids:
                layer_status = "Upload complete. New files are selected in the layer selectors; load and zoom each one before collecting GCPs."
            else:
                layer_status = "No new layer was successfully registered."
        elif triggered == "admin-refresh":
            layer_status = "Layer availability and signed map URLs refreshed."
        else:
            layer_status = "Layer selection updated. Load and zoom each layer before collecting GCPs."

        # Ensure loaded rasters use the latest slider values even when the
        # sliders were moved before the overlay was loaded.
        state["reference_registry"] = _apply_opacity(
            state.get("reference_registry", []),
            next_loaded.get("reference_loaded_db_layer_id"),
            reference_opacity,
        )
        state["historical_registry"] = _apply_opacity(
            state.get("historical_registry", []),
            next_loaded.get("historical_loaded_db_layer_id"),
            historical_opacity,
        )

        reference_children = _layer_control(state, "reference", next_loaded.get("reference_loaded_db_layer_id"))
        historical_children = _layer_control(state, "historical", next_loaded.get("historical_loaded_db_layer_id"))

        ref_indicator = _layer_indicator(
            selected_ref,
            next_loaded.get("reference_loaded_db_layer_id"),
            next_loaded.get("reference_db_layer_id"),
        )
        hist_indicator = _layer_indicator(
            selected_hist,
            next_loaded.get("historical_loaded_db_layer_id"),
            next_loaded.get("historical_db_layer_id"),
        )
        collection_ready = bool(next_loaded.get("reference_db_layer_id") and next_loaded.get("historical_db_layer_id"))

        if triggered in {"admin-refresh", "admin-upload-layers"}:
            if not collection_ready:
                layer_status += " GCP collection remains disabled until both loaded layers have been zoomed/activated."

        return (
            reference_children,
            historical_children,
            state,
            state if triggered in {"admin-refresh", "admin-upload-layers"} else no_update,
            reference_options,
            selected_ref,
            historical_options,
            selected_hist,
            next_loaded,
            layer_status,
            upload_status,
            not collection_ready,
            _availability_details(state.get("unavailable_layers") or []),
            viewport_request,
            ref_indicator,
            hist_indicator,
        )

    @app.callback(
        Output({"type": "reference-raster-layer", "index": ALL}, "opacity"),
        Input("admin-reference-opacity", "value"),
        Input({"type": "reference-raster-layer", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def set_reference_raster_opacity(value, layer_ids):
        opacity = max(0.0, min(1.0, float(value if value is not None else 75) / 100.0))
        return [opacity for _ in (layer_ids or [])]

    @app.callback(
        Output({"type": "historical-raster-layer", "index": ALL}, "opacity"),
        Input("admin-historical-opacity", "value"),
        Input({"type": "historical-raster-layer", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def set_historical_raster_opacity(value, layer_ids):
        opacity = max(0.0, min(1.0, float(value if value is not None else 75) / 100.0))
        return [opacity for _ in (layer_ids or [])]

    @app.callback(
        Output("admin-reference-upload-filename", "children"),
        Output("admin-historical-upload-filename", "children"),
        Input("admin-reference-upload", "filename"),
        Input("admin-historical-upload", "filename"),
    )
    def display_selected_upload_names(reference_filename, historical_filename):
        def label(filename):
            if not filename:
                return "No file selected"
            safe_name = Path(str(filename).replace("\\", "/")).name
            return f"Selected: {safe_name}"
        return label(reference_filename), label(historical_filename)

from __future__ import annotations

from pathlib import Path

import rasterio
from dash import Input, Output, State, ctx, no_update
from flask import abort
from flask_login import current_user

from maps.raster import prepare_uploaded_raster
from services.admin_layers import (
    build_admin_layer_state,
    build_admin_selected_layer_control_children,
)


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _option_exists(options: list[dict], value) -> bool:
    return value not in (None, "") and any(
        str(item.get("value")) == str(value) for item in (options or [])
    )


def _first_option(options: list[dict]):
    return options[0].get("value") if options else None


def _layer_name(state: dict, kind: str, db_layer_id) -> str:
    if db_layer_id in (None, ""):
        return "not selected"
    if kind == "reference":
        options = state.get("reference_options", [])
    else:
        options = state.get("available_historical_options", [])
    selected = next((item for item in options if str(item.get("value")) == str(db_layer_id)), None)
    return selected.get("label", str(db_layer_id)) if selected else str(db_layer_id)


def _layer_control(state: dict, kind: str, db_layer_id):
    return build_admin_selected_layer_control_children(
        state.get(f"{kind}_registry", []),
        kind,
        db_layer_id,
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


def register_admin_layer_callbacks(app, layer_store):
    """Manage existing and newly uploaded layers for the Admin GCP workspace.

    This is the single callback owner for the two Leaflet layer controls. The
    Step 1 GCP filter callbacks only manage GCP data, avoiding duplicate Dash
    outputs and keeping the currently loaded layer selection stable.
    """

    @app.callback(
        Output("reference-layer-control", "children"),
        Output("historical-layer-control", "children"),
        Output("admin-selection-layer-state", "data"),
        Output("admin-reference-existing-select", "options"),
        Output("admin-reference-existing-select", "value"),
        Output("admin-historical-existing-select", "options"),
        Output("admin-historical-existing-select", "value"),
        Output("admin-loaded-layer-selection", "data"),
        Output("admin-layer-load-status", "children"),
        Output("admin-upload-status", "children"),
        Output("admin-add-gcp-button", "disabled"),
        Output("admin-unavailable-layer-note", "children"),
        Input("admin-load-selected-layers", "n_clicks"),
        Input("admin-upload-layers", "n_clicks"),
        Input("admin-refresh", "n_clicks"),
        State("admin-reference-existing-select", "value"),
        State("admin-historical-existing-select", "value"),
        State("admin-reference-upload", "contents"),
        State("admin-reference-upload", "filename"),
        State("admin-historical-upload", "contents"),
        State("admin-historical-upload", "filename"),
        State("admin-loaded-layer-selection", "data"),
        prevent_initial_call=True,
    )
    def manage_admin_layers(
        load_clicks,
        upload_clicks,
        refresh_clicks,
        reference_choice,
        historical_choice,
        reference_contents,
        reference_filename,
        historical_contents,
        historical_filename,
        loaded_selection,
    ):
        del load_clicks, upload_clicks, refresh_clicks
        _require_admin()
        triggered = ctx.triggered_id
        loaded_selection = loaded_selection or {}

        # Upload one or both files independently. A successful upload is kept
        # even if the other selected file fails validation/conversion.
        uploaded_ids: dict[str, str] = {}
        upload_messages: list[str] = []
        if triggered == "admin-upload-layers":
            selected_files = [
                ("reference", reference_contents, reference_filename),
                ("historical", historical_contents, historical_filename),
            ]
            if not any(contents and filename for _kind, contents, filename in selected_files):
                return (
                    no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update, no_update,
                    "Choose a reference GeoTIFF, a historical GeoTIFF, or both before uploading.",
                    no_update,
                    no_update,
                )
            for kind, contents, filename in selected_files:
                if not contents or not filename:
                    continue
                try:
                    db_id, safe_name = _upload_one(contents, filename, kind, layer_store)
                    uploaded_ids[kind] = db_id
                    upload_messages.append(f"Uploaded {kind}: {safe_name}")
                except Exception as exc:
                    upload_messages.append(f"{kind.title()} upload failed: {exc}")

        try:
            # Always re-check the real cache and regenerate time-limited signed
            # TiTiler URLs before showing or loading a raster.
            layer_state = build_admin_layer_state(layer_store)
        except Exception as exc:
            return (
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                f"Could not inspect registered layers: {exc}",
                "; ".join(upload_messages) if upload_messages else no_update,
                no_update,
                no_update,
            )

        reference_options = layer_state.get("reference_options", [])
        historical_options = layer_state.get("available_historical_options", [])

        previous_ref = loaded_selection.get("reference_db_layer_id")
        previous_hist = loaded_selection.get("historical_db_layer_id")

        if triggered == "admin-upload-layers":
            selected_ref = (
                uploaded_ids.get("reference")
                or reference_choice
                or previous_ref
                or _first_option(reference_options)
            )
            selected_hist = (
                uploaded_ids.get("historical")
                or historical_choice
                or previous_hist
                or _first_option(historical_options)
            )
        elif triggered == "admin-load-selected-layers":
            selected_ref = reference_choice
            selected_hist = historical_choice
        else:  # admin-refresh
            selected_ref = previous_ref or reference_choice or _first_option(reference_options)
            selected_hist = previous_hist or historical_choice or _first_option(historical_options)

        ref_valid = _option_exists(reference_options, selected_ref)
        hist_valid = _option_exists(historical_options, selected_hist)

        # Expired/missing rasters are excluded by build_admin_layer_state. If a
        # previously loaded raster has disappeared, remove it from the map and
        # clear its selection instead of leaving a broken tile URL in Leaflet.
        map_reference_id = selected_ref if ref_valid else None
        map_historical_id = selected_hist if hist_valid else None

        if triggered == "admin-load-selected-layers" and not (ref_valid and hist_valid):
            status = "Select one available reference layer and one available historical layer, then load them."
            # A failed/partial selection must not half-switch the maps. Keep
            # the currently loaded pair where those layers are still usable.
            previous_ref_valid = _option_exists(reference_options, previous_ref)
            previous_hist_valid = _option_exists(historical_options, previous_hist)
            map_reference_id = previous_ref if previous_ref_valid else None
            map_historical_id = previous_hist if previous_hist_valid else None
            next_loaded = {
                "reference_db_layer_id": str(previous_ref) if previous_ref_valid else None,
                "historical_db_layer_id": str(previous_hist) if previous_hist_valid else None,
            }
        else:
            next_loaded = {
                "reference_db_layer_id": str(map_reference_id) if map_reference_id is not None else None,
                "historical_db_layer_id": str(map_historical_id) if map_historical_id is not None else None,
            }
            if triggered == "admin-load-selected-layers":
                status = (
                    f"Loaded reference: {_layer_name(layer_state, 'reference', selected_ref)} · "
                    f"historical: {_layer_name(layer_state, 'historical', selected_hist)}. "
                    "You can now start collecting GCPs."
                )
            elif triggered == "admin-upload-layers":
                status = (
                    "Uploaded layers are ready. "
                    if uploaded_ids
                    else "No uploaded layer could be registered. "
                )
                if selected_ref and selected_hist:
                    status += "The selected reference and historical layers are loaded."
                else:
                    status += "Choose an available reference and historical layer, then load them."
            else:
                status = "Layer availability and map URLs refreshed."
                missing = []
                if not ref_valid:
                    missing.append("reference")
                if not hist_valid:
                    missing.append("historical")
                if missing:
                    status += " Previously loaded " + " and ".join(missing) + " raster is unavailable; select another."

        reference_children = _layer_control(layer_state, "reference", map_reference_id)
        historical_children = _layer_control(layer_state, "historical", map_historical_id)
        upload_status = "; ".join(upload_messages) if upload_messages else no_update
        if triggered == "admin-upload-layers" and not upload_messages:
            upload_status = "No files were uploaded."

        return (
            reference_children,
            historical_children,
            layer_state,
            reference_options,
            selected_ref,
            historical_options,
            selected_hist,
            next_loaded,
            status,
            upload_status,
            not bool(next_loaded.get("reference_db_layer_id") and next_loaded.get("historical_db_layer_id")),
            ("Unavailable layers are retained in the database but are not offered for loading: " + "; ".join(layer_state.get("unavailable_layers") or [])) if layer_state.get("unavailable_layers") else "All registered uploaded raster files are currently available.",
        )

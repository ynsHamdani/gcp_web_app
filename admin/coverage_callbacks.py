from __future__ import annotations

import csv
import io
import json

from dash import Input, Output, State, ctx, dcc, html, no_update
from flask import abort
from flask_login import current_user

from services.coverage_assignment import leaflet_bounds_to_dict
from services.coverage_import import CoverageImportError, inspect_coverage_upload
from ui.admin_coverage_layout import _feature_rows, _registry_rows

_EMPTY_FC = {"type": "FeatureCollection", "features": []}


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _validation_report(import_data):
    warnings = [html.Li(message, style={"marginBottom": "4px"}) for message in import_data.warnings]
    return html.Div([
        html.Div("Validation passed · prepared for publication", style={"fontSize": "13px", "fontWeight": "800", "color": "#166534", "marginBottom": "7px"}),
        html.Div([
            html.Span(f"{import_data.feature_count:,} polygon features", style={"fontWeight": "700"}),
            html.Span(f" · {import_data.geometry_type}"),
            html.Span(f" · source {import_data.source_crs}"),
            html.Span(f" · storage EPSG:{import_data.target_srid}"),
        ], style={"fontSize": "12px", "color": "#334155", "lineHeight": "1.6"}),
        html.Div(
            f"Source layer: {import_data.source_layer_name or 'default layer'} · SHA-256: {import_data.source_sha256[:16]}…",
            style={"fontSize": "11px", "color": "#64748b", "marginTop": "4px", "overflowWrap": "anywhere"},
        ),
        html.Ul(warnings, style={"fontSize": "11px", "color": "#92400e", "paddingLeft": "20px", "margin": "8px 0 0"}) if warnings else html.Div(
            "No validation warnings.", style={"fontSize": "11px", "color": "#166534", "marginTop": "7px"}
        ),
        html.Div("Publishing will reuse this prepared data; the source file will not be re-read or reprojected.", style={"fontSize": "11px", "color": "#166534", "marginTop": "7px"}),
    ], style={"padding": "12px", "background": "#f0fdf4", "border": "1px solid #bbf7d0", "borderRadius": "8px"})


def _error_report(title: str, message: str):
    return html.Div([
        html.Div(title, style={"fontWeight": "800", "color": "#991b1b", "marginBottom": "5px"}),
        html.Div(message, style={"fontSize": "12px", "lineHeight": "1.5", "color": "#7f1d1d"}),
    ], style={"padding": "12px", "background": "#fef2f2", "border": "1px solid #fecaca", "borderRadius": "8px"})


def _layer_options(layers: list[dict], *, selectable: bool) -> list[dict]:
    result = []
    for item in layers:
        if selectable and (not item.get("is_active") or item.get("is_suppressed")):
            continue
        if item.get("is_suppressed"):
            status = "Suppressed"
        elif item.get("is_active"):
            status = "Active"
        else:
            status = "Archived"
        result.append({
            "label": f"{item['layer_name']} · v{item['version']} · {status}",
            "value": str(item["coverage_layer_id"]),
        })
    return result


def _summary_cards(summary: dict | None):
    if not summary:
        return html.Div("Run an assignment to calculate the coverage summary.", style={"color": "#64748b", "fontSize": "12px"})
    not_unique = int(summary["uncovered"]) + int(summary["multiple_matches"])
    cards = (
        ("GCPs examined", summary["total_gcps"]),
        ("Assigned uniquely", summary["assigned_unique"]),
        ("Not uniquely assigned", not_unique),
    )
    return html.Div([
        html.Div([
            html.Div(f"{value:,}", style={"fontSize": "25px", "fontWeight": "800", "fontVariantNumeric": "tabular-nums"}),
            html.Div(label, style={"fontSize": "11px", "color": "#64748b"}),
        ], style={"background": "#f8fafc", "border": "1px solid #e2e8f0", "borderRadius": "9px", "padding": "11px"})
        for label, value in cards
    ] + [
        html.Div(
            f"Not uniquely assigned — diagnostics: {int(summary['uncovered']):,} uncovered · {int(summary['multiple_matches']):,} multiple matches",
            style={"gridColumn": "1 / -1", "fontSize": "11px", "color": "#64748b", "padding": "2px 1px"},
        )
    ], style={"display": "grid", "gridTemplateColumns": "repeat(3, minmax(0, 1fr))", "gap": "8px"})


def _csv_download(rows: list[dict], columns: list[str], filename: str):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        clean = dict(row)
        for key in ("context_breakdown", "attributes"):
            if isinstance(clean.get(key), (dict, list)):
                clean[key] = json.dumps(clean[key], ensure_ascii=False, sort_keys=True)
        writer.writerow(clean)
    return dcc.send_bytes(buffer.getvalue().encode("utf-8-sig"), filename)


def register_coverage_callbacks(app, coverage_store, staging_store) -> None:
    """Register coverage import lifecycle, spatial assignment and map callbacks."""

    # Validate once, write the normalized geometry to private server-side
    # staging, and pass only a short opaque token through browser state.
    @app.callback(
        Output("coverage-upload-filename", "children"),
        Output("coverage-validation-report", "children"),
        Output("coverage-validation-state", "data"),
        Input("coverage-validate-button", "n_clicks"),
        Input("coverage-file-upload", "contents"),
        Input("coverage-file-upload", "filename"),
        State("coverage-validation-state", "data"),
        prevent_initial_call=True,
    )
    def validate_file(n_clicks, contents, filename, previous_state):
        _require_admin()
        previous_token = (previous_state or {}).get("stage_token")
        if ctx.triggered_id == "coverage-file-upload":
            # A new file invalidates any previously prepared token. Remove
            # its staged bytes immediately instead of waiting for the TTL.
            if previous_token:
                try:
                    staging_store.delete(previous_token)
                except ValueError:
                    pass
            selected = f"Selected: {filename}" if filename else "No file selected."
            report = html.Div("The selected file changed. Validate and prepare it before publishing.", style={"fontSize": "12px", "color": "#92400e"})
            return selected, report, {"valid": False, "filename": filename}
        if not n_clicks:
            return no_update, no_update, no_update
        # Revalidation replaces the former staged result.
        if previous_token:
            try:
                staging_store.delete(previous_token)
            except ValueError:
                pass
        if not contents or not filename:
            return "No file selected.", _error_report("Validation failed", "Choose a GeoPackage, GeoJSON or zipped Shapefile first."), {"valid": False}
        try:
            data = inspect_coverage_upload(contents, filename)
            token, _metadata = staging_store.stage(data)
            state = data.validation_state()
            state.update({"stage_token": token})
            return f"Prepared: {data.filename}", _validation_report(data), state
        except (CoverageImportError, ValueError) as exc:
            return f"Selected: {filename}", _error_report("Validation failed", str(exc)), {"valid": False, "filename": str(filename)}
        except Exception as exc:
            return f"Selected: {filename}", _error_report("Validation failed", f"The file could not be prepared: {exc}"), {"valid": False, "filename": str(filename)}

    @app.callback(
        Output("coverage-publish-status", "children"),
        Output("coverage-published-event", "data"),
        Input("coverage-publish-button", "n_clicks"),
        State("coverage-file-upload", "filename"),
        State("coverage-layer-name", "value"),
        State("coverage-layer-notes", "value"),
        State("coverage-validation-state", "data"),
        prevent_initial_call=True,
        running=[
            (Output("coverage-publish-button", "disabled"), True, False),
            (Output("coverage-validate-button", "disabled"), True, False),
            (Output("coverage-file-upload", "disabled"), True, False),
            (Output("coverage-publish-loading", "style"),
             {"display": "flex", "alignItems": "center", "gap": "10px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "12px"},
             {"display": "none", "alignItems": "center", "gap": "10px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "12px"}),
        ],
    )
    def publish_file(n_clicks, filename, layer_name, notes, validation_state):
        if not n_clicks:
            return no_update, no_update
        _require_admin()
        try:
            if not validation_state or not validation_state.get("valid"):
                raise ValueError("Validate the selected file before publishing it.")
            if not filename or filename != validation_state.get("filename"):
                raise ValueError("The selected file changed after validation. Validate the current file again.")
            token = validation_state.get("stage_token")
            if not token:
                raise ValueError("The prepared import token is missing. Validate the file again.")

            # Fast idempotent retry path: a completed first request may already
            # have removed its stage file, but its token remains in the DB.
            published = coverage_store.get_publication(token)
            if published is None:
                staged = staging_store.open(token)
                if staged.source_sha256 != validation_state.get("source_sha256"):
                    raise ValueError("The prepared import does not match the validation result. Validate again.")
                published = coverage_store.publish_import(
                    layer_name=layer_name,
                    notes=notes or "",
                    import_data=staged,
                    imported_by=int(current_user.get_id()),
                    publish_token=token,
                )
            staging_store.delete(token)
            suffix = " This was an idempotent retry; no duplicate features were inserted." if published.get("already_published") else ""
            status = html.Div(
                f"Published '{published['layer_name']}' version {published['version']} with {published['feature_count']:,} features.{suffix}",
                style={"padding": "10px 12px", "border": "1px solid #bbf7d0", "borderRadius": "8px", "background": "#f0fdf4", "color": "#166534", "lineHeight": "1.5"},
            )
            event = {"coverage_layer_id": published["coverage_layer_id"], "request_token": token}
            return status, event
        except Exception as exc:
            return _error_report("Publication failed", str(exc)), no_update

    # Delete requires a second explicit confirmation and retains the selected
    # target in a store so changing the dropdown cannot redirect the operation.
    @app.callback(
        Output("coverage-delete-confirm", "displayed"),
        Output("coverage-delete-confirm", "message"),
        Output("coverage-delete-target", "data"),
        Input("coverage-delete-button", "n_clicks"),
        State("coverage-management-layer", "value"),
        prevent_initial_call=True,
    )
    def request_delete(n_clicks, selected_layer_id):
        if not n_clicks:
            return no_update, no_update, no_update
        _require_admin()
        if not selected_layer_id:
            return False, "Select a coverage version first.", None
        layer = coverage_store.get_layer(selected_layer_id)
        if not layer:
            return False, "The selected coverage version no longer exists.", None
        target = {"coverage_layer_id": str(layer["coverage_layer_id"]), "layer_name": layer["layer_name"], "version": layer["version"]}
        message = (
            f"Permanently delete '{layer['layer_name']}' version {layer['version']} "
            f"and its {layer['stored_feature_count']:,} polygon features? This cannot be undone."
        )
        return True, message, target

    # One registry refresh/action callback keeps table and dropdowns consistent.
    @app.callback(
        Output("coverage-registry-body", "children"),
        Output("coverage-management-layer", "options"),
        Output("coverage-analysis-layer", "options"),
        Output("coverage-analysis-layer", "value"),
        Output("coverage-management-status", "children"),
        Input("coverage-refresh-button", "n_clicks"),
        Input("coverage-suppress-button", "n_clicks"),
        Input("coverage-reactivate-button", "n_clicks"),
        Input("coverage-delete-confirm", "submit_n_clicks"),
        Input("coverage-published-event", "data"),
        State("coverage-management-layer", "value"),
        State("coverage-delete-target", "data"),
        State("coverage-analysis-layer", "value"),
        prevent_initial_call=True,
    )
    def manage_registry(_refresh, _suppress, _reactivate, _delete, _published, managed_id, delete_target, analysis_id):
        _require_admin()
        triggered = ctx.triggered_id
        message = "Registry refreshed."
        try:
            if triggered == "coverage-suppress-button":
                if not managed_id:
                    raise ValueError("Select a coverage version first.")
                layer = coverage_store.suppress_layer(managed_id)
                message = f"Suppressed '{layer['layer_name']}' version {layer['version']}."
            elif triggered == "coverage-reactivate-button":
                if not managed_id:
                    raise ValueError("Select a coverage version first.")
                layer = coverage_store.activate_layer(managed_id)
                message = f"Activated '{layer['layer_name']}' version {layer['version']}. Other versions with the same name are now archived."
            elif triggered == "coverage-delete-confirm":
                if not delete_target:
                    raise ValueError("The confirmed deletion target is missing. Select the version again.")
                layer = coverage_store.delete_layer(delete_target["coverage_layer_id"])
                message = f"Deleted '{layer['layer_name']}' version {layer['version']} and its polygon features."
            elif triggered == "coverage-published-event":
                message = "New coverage version published. It is selected for analysis."

            layers = coverage_store.list_layers()
            management_options = _layer_options(layers, selectable=False)
            analysis_options = _layer_options(layers, selectable=True)
            available_analysis_ids = {str(item["value"]) for item in analysis_options}
            published_id = str((_published or {}).get("coverage_layer_id") or "") if triggered == "coverage-published-event" else ""
            selected_analysis = published_id if published_id in available_analysis_ids else (str(analysis_id) if analysis_id is not None else None)
            if selected_analysis not in available_analysis_ids:
                selected_analysis = analysis_options[0]["value"] if analysis_options else None
            return _registry_rows(layers), management_options, analysis_options, selected_analysis, message
        except Exception as exc:
            layers = coverage_store.list_layers()
            management_options = _layer_options(layers, selectable=False)
            analysis_options = _layer_options(layers, selectable=True)
            selected_analysis = str(analysis_id) if analysis_id and any(str(i["value"]) == str(analysis_id) for i in analysis_options) else (analysis_options[0]["value"] if analysis_options else None)
            return _registry_rows(layers), management_options, analysis_options, selected_analysis, f"Registry action failed: {exc}"

    # Update the map extent when the administrator changes the selected layer.
    @app.callback(
        Output("coverage-map", "bounds"),
        Input("coverage-analysis-layer", "value"),
        prevent_initial_call=True,
    )
    def zoom_to_coverage_layer(layer_id):
        _require_admin()
        if not layer_id:
            return no_update
        bounds = coverage_store.get_layer_bounds(layer_id)
        return bounds if bounds else no_update

    # Viewport-scoped rendering. The store refuses to return a partial polygon
    # set when a viewport contains too many features; it asks the admin to zoom.
    @app.callback(
        Output("coverage-polygons", "data"),
        Output("coverage-gcp-points", "data"),
        Output("coverage-map-status", "children"),
        Input("coverage-map", "bounds"),
        Input("coverage-map", "zoom"),
        Input("coverage-analysis-layer", "value"),
        prevent_initial_call=False,
    )
    def update_coverage_map(bounds, zoom, layer_id):
        _require_admin()
        if not layer_id:
            return _EMPTY_FC, _EMPTY_FC, "Select an active coverage version to display it."
        try:
            normalized = leaflet_bounds_to_dict(bounds)
            result = coverage_store.query_map_geojson(layer_id, normalized, zoom=zoom or 10)
            if result["too_many_features"]:
                return _EMPTY_FC, _EMPTY_FC, (
                    f"This view contains more than {result['feature_count_in_view'] - 1:,} polygons. "
                    "Zoom in to load a clearer, complete view; the application will not silently show only part of the layer."
                )
            point_note = " GCP markers were capped at 3,000 in this view." if result.get("points_limited") else ""
            return (
                result["polygons"], result["points"],
                f"Showing {result['feature_count_in_view']:,} polygon(s) and {len(result['points']['features']):,} GCP(s) in the current viewport.{point_note}",
            )
        except Exception as exc:
            return _EMPTY_FC, _EMPTY_FC, f"Map data could not be loaded: {exc}"

    # Assignment summary and feature table use the same unique-match SQL.
    @app.callback(
        Output("coverage-assignment-summary", "children"),
        Output("coverage-feature-table-body", "children"),
        Output("coverage-feature-page", "data"),
        Output("coverage-feature-page-label", "children"),
        Output("coverage-analysis-status", "children"),
        Output("coverage-analysis-state", "data"),
        Input("coverage-run-analysis", "n_clicks"),
        Input("coverage-feature-prev", "n_clicks"),
        Input("coverage-feature-next", "n_clicks"),
        Input("coverage-analysis-layer", "value"),
        State("coverage-feature-page", "data"),
        State("coverage-analysis-state", "data"),
        prevent_initial_call=True,
        running=[
            (Output("coverage-run-analysis", "disabled"), True, False),
            (Output("coverage-analysis-loading", "style"),
             {"display": "flex", "alignItems": "center", "gap": "10px", "fontSize": "12px", "color": "#1d4ed8", "marginBottom": "10px"},
             {"display": "none", "alignItems": "center", "gap": "10px", "fontSize": "12px", "color": "#1d4ed8", "marginBottom": "10px"}),
        ],
    )
    def run_or_page_analysis(_run, _prev, _next, layer_id, current_page, analysis_state):
        _require_admin()
        triggered = ctx.triggered_id
        if triggered == "coverage-analysis-layer":
            return (
                _summary_cards(None),
                [html.Tr(html.Td("Run the assignment to load feature statistics.", colSpan=5, style={"padding": "18px", "textAlign": "center", "color": "#64748b"}))],
                0, "Page 0 of 0", "Coverage version changed. Run the assignment to refresh statistics.", None,
            )
        if not layer_id:
            return _summary_cards(None), [], 0, "Page 0 of 0", "Select an active coverage version first.", None
        page = 0 if triggered == "coverage-run-analysis" else max(0, int(current_page or 0))
        if triggered == "coverage-feature-prev":
            page = max(0, page - 1)
        elif triggered == "coverage-feature-next":
            page += 1
        try:
            same_analysis = bool(analysis_state and str(analysis_state.get("coverage_layer_id")) == str(layer_id))
            summary = (analysis_state or {}).get("summary") if same_analysis and triggered != "coverage-run-analysis" else None
            if summary is None:
                summary = coverage_store.assignment_summary(layer_id)
            page_rows, total_features = coverage_store.feature_statistics(layer_id, page=page, page_size=50)
            max_page = max(0, (total_features - 1) // 50)
            if page > max_page:
                page = max_page
                page_rows, _ = coverage_store.feature_statistics(layer_id, page=page, page_size=50)
            state = {"coverage_layer_id": str(layer_id), "summary": summary}
            label = f"Page {page + 1} of {max_page + 1} · {total_features:,} coverage features"
            return (
                _summary_cards(summary), _feature_rows(page_rows), page, label,
                "Unique assignment complete. One polygon is assigned only when exactly one polygon covers the GCP reference point.",
                state,
            )
        except Exception as exc:
            return _summary_cards(None), [], page, "Page unavailable", f"Assignment/statistics failed: {exc}", analysis_state

    @app.callback(
        Output("coverage-export-features", "disabled"),
        Output("coverage-export-assignments", "disabled"),
        Input("coverage-analysis-state", "data"),
        Input("coverage-analysis-layer", "value"),
    )
    def set_export_enabled(analysis_state, selected_layer_id):
        valid = bool(
            analysis_state
            and selected_layer_id
            and str(analysis_state.get("coverage_layer_id")) == str(selected_layer_id)
        )
        return not valid, not valid

    @app.callback(
        Output("coverage-feature-download", "data"),
        Input("coverage-export-features", "n_clicks"),
        State("coverage-analysis-state", "data"),
        State("coverage-analysis-layer", "value"),
        prevent_initial_call=True,
    )
    def export_features(n_clicks, analysis_state, selected_layer_id):
        if not n_clicks:
            return no_update
        _require_admin()
        if not analysis_state or str(analysis_state.get("coverage_layer_id")) != str(selected_layer_id):
            raise ValueError("Run the assignment for the currently selected coverage version before exporting.")
        layer_id = analysis_state["coverage_layer_id"]
        layer = coverage_store.get_layer(layer_id)
        rows = coverage_store.export_feature_statistics(layer_id)
        enriched = [{
            **row,
            "coverage_layer_id": layer_id,
            "coverage_layer_name": layer["layer_name"] if layer else "",
            "coverage_layer_version": layer["version"] if layer else "",
            "assignment_rule": "ST_Covers; assign only when match_count = 1",
        } for row in rows]
        return _csv_download(enriched, ["coverage_layer_id", "coverage_layer_name", "coverage_layer_version", "assignment_rule", "coverage_feature_id", "source_feature_key", "feature_label", "assigned_count", "context_breakdown", "attributes"], "coverage_feature_statistics.csv")

    @app.callback(
        Output("coverage-assignment-download", "data"),
        Input("coverage-export-assignments", "n_clicks"),
        State("coverage-analysis-state", "data"),
        State("coverage-analysis-layer", "value"),
        prevent_initial_call=True,
    )
    def export_assignments(n_clicks, analysis_state, selected_layer_id):
        if not n_clicks:
            return no_update
        _require_admin()
        if not analysis_state or str(analysis_state.get("coverage_layer_id")) != str(selected_layer_id):
            raise ValueError("Run the assignment for the currently selected coverage version before exporting.")
        layer_id = analysis_state["coverage_layer_id"]
        layer = coverage_store.get_layer(layer_id)
        rows = coverage_store.export_gcp_assignments(layer_id)
        enriched = [{
            **row,
            "coverage_layer_id": layer_id,
            "coverage_layer_name": layer["layer_name"] if layer else "",
            "coverage_layer_version": layer["version"] if layer else "",
            "assignment_rule": "ST_Covers; assign only when match_count = 1",
        } for row in rows]
        return _csv_download(enriched, ["coverage_layer_id", "coverage_layer_name", "coverage_layer_version", "assignment_rule", "gcp_id", "assignment_status", "assignment_reason", "match_count", "coverage_feature_id", "context_category_code", "context_category_label"], "gcp_coverage_assignments.csv")

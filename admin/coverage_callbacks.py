from __future__ import annotations

from dash import Input, Output, State, html, no_update
from flask import abort
from flask_login import current_user

from services.coverage_import import CoverageImportError, inspect_coverage_upload
from ui.admin_coverage_layout import _registry_rows


def _require_admin() -> None:
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "admin":
        abort(403)


def _validation_report(import_data):
    warnings = [
        html.Li(message, style={"marginBottom": "4px"})
        for message in import_data.warnings
    ]
    return html.Div([
        html.Div(
            "Validation passed",
            style={"fontSize": "13px", "fontWeight": "800", "color": "#166534", "marginBottom": "7px"},
        ),
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
    ], style={"padding": "12px", "background": "#f0fdf4", "border": "1px solid #bbf7d0", "borderRadius": "8px"})


def _error_report(message: str):
    return html.Div([
        html.Div("Validation failed", style={"fontWeight": "800", "color": "#991b1b", "marginBottom": "5px"}),
        html.Div(message, style={"fontSize": "12px", "lineHeight": "1.5", "color": "#7f1d1d"}),
    ], style={"padding": "12px", "background": "#fef2f2", "border": "1px solid #fecaca", "borderRadius": "8px"})


def register_coverage_callbacks(app, coverage_store) -> None:
    """Register validation, atomic publish and registry-refresh callbacks."""

    @app.callback(
        Output("coverage-upload-filename", "children"),
        Output("coverage-validation-report", "children"),
        Output("coverage-validation-state", "data"),
        Output("coverage-publish-button", "disabled"),
        Input("coverage-validate-button", "n_clicks"),
        State("coverage-file-upload", "contents"),
        State("coverage-file-upload", "filename"),
        prevent_initial_call=True,
    )
    def validate_file(n_clicks, contents, filename):
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        _require_admin()
        if not contents or not filename:
            message = "Choose a GeoPackage, GeoJSON or zipped Shapefile first."
            return "No file selected.", _error_report(message), {"valid": False}, True
        try:
            data = inspect_coverage_upload(contents, filename)
            return (
                f"Selected: {data.filename}",
                _validation_report(data),
                data.validation_state(),
                False,
            )
        except (CoverageImportError, ValueError) as exc:
            return (
                f"Selected: {filename}",
                _error_report(str(exc)),
                {"valid": False, "filename": str(filename)},
                True,
            )
        except Exception as exc:
            # Keep errors visible but do not expose stack traces or SQL details.
            return (
                f"Selected: {filename}",
                _error_report(f"The file could not be validated: {exc}"),
                {"valid": False, "filename": str(filename)},
                True,
            )

    @app.callback(
        Output("coverage-publish-status", "children"),
        Input("coverage-publish-button", "n_clicks"),
        State("coverage-file-upload", "contents"),
        State("coverage-file-upload", "filename"),
        State("coverage-layer-name", "value"),
        State("coverage-layer-notes", "value"),
        State("coverage-validation-state", "data"),
        prevent_initial_call=True,
    )
    def publish_file(n_clicks, contents, filename, layer_name, notes, validation_state):
        if not n_clicks:
            return no_update
        _require_admin()
        try:
            if not validation_state or not validation_state.get("valid"):
                raise ValueError("Validate the selected file before publishing it.")
            if not contents or not filename:
                raise ValueError("The selected file is no longer available. Upload it again and validate it.")
            data = inspect_coverage_upload(contents, filename)
            if (
                data.source_sha256 != validation_state.get("source_sha256")
                or data.filename != validation_state.get("filename")
            ):
                raise ValueError("The selected file changed after validation. Validate the current file again.")
            published = coverage_store.publish_import(
                layer_name=layer_name,
                notes=notes or "",
                import_data=data,
                imported_by=int(current_user.get_id()),
            )
            return html.Div(
                f"Published '{published['layer_name']}' version {published['version']} "
                f"with {published['feature_count']:,} features. The previous version, if any, is retained as archived.",
                style={"padding": "10px 12px", "border": "1px solid #bbf7d0", "borderRadius": "8px", "background": "#f0fdf4", "color": "#166534", "lineHeight": "1.5"},
            )
        except Exception as exc:
            return html.Div(
                str(exc),
                style={"padding": "10px 12px", "border": "1px solid #fecaca", "borderRadius": "8px", "background": "#fef2f2", "color": "#991b1b", "lineHeight": "1.5"},
            )

    @app.callback(
        Output("coverage-registry-body", "children"),
        Input("coverage-refresh-button", "n_clicks"),
        Input("coverage-publish-button", "n_clicks"),
    )
    def refresh_registry(_refresh_clicks, _publish_clicks):
        _require_admin()
        return _registry_rows(coverage_store.list_layers())

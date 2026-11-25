from __future__ import annotations

import json

import dash_leaflet as dl
from dash import dcc, html
from dash_extensions.javascript import Namespace

from maps.map_views import create_layers_control
from services.coverage_assignment import context_breakdown_label
from ui.admin_nav import create_page_shell

_EMPTY_FC = {"type": "FeatureCollection", "features": []}
_CARD_STYLE = {
    "background": "#ffffff", "border": "1px solid #dbe2ea",
    "borderRadius": "12px", "padding": "16px",
    "boxShadow": "0 1px 3px rgba(15,23,42,0.04)",
}
_LABEL_STYLE = {"display": "block", "fontSize": "12px", "fontWeight": "700", "color": "#334155", "marginBottom": "6px"}
_INPUT_STYLE = {"width": "100%", "boxSizing": "border-box", "padding": "9px 10px", "border": "1px solid #cbd5e1", "borderRadius": "7px", "fontSize": "13px"}
_BUTTON_STYLE = {"border": "0", "borderRadius": "7px", "padding": "9px 13px", "fontSize": "12px", "fontWeight": "700", "cursor": "pointer"}
_HEADER_CELL = {"textAlign": "left", "fontSize": "11px", "padding": "9px 10px", "background": "#f8fafc", "whiteSpace": "nowrap", "borderBottom": "1px solid #e2e8f0"}
_BODY_CELL = {"fontSize": "11px", "padding": "8px 10px", "borderBottom": "1px solid #eef2f7", "verticalAlign": "top"}


def _registry_rows(layers: list[dict]):
    if not layers:
        return [html.Tr(html.Td("No coverage layers have been imported yet.", colSpan=10, style={**_BODY_CELL, "padding": "18px", "textAlign": "center", "color": "#64748b"}))]
    rows = []
    for item in layers:
        if item.get("is_suppressed"):
            status, status_color = "Suppressed", "#b45309"
        elif item.get("is_active"):
            status, status_color = "Active", "#166534"
        else:
            status, status_color = "Archived", "#64748b"
        rows.append(html.Tr([
            html.Td(item.get("layer_name", ""), style={**_BODY_CELL, "fontWeight": "700"}),
            html.Td(f"v{item.get('version', '')}", style=_BODY_CELL),
            html.Td(status, style={**_BODY_CELL, "color": status_color, "fontWeight": "700"}),
            html.Td(f"{item.get('stored_feature_count', 0):,} / {item.get('feature_count', 0):,}", style={**_BODY_CELL, "fontVariantNumeric": "tabular-nums"}),
            html.Td(item.get("source_format", ""), style=_BODY_CELL),
            html.Td(item.get("source_crs", ""), style=_BODY_CELL),
            html.Td(f"EPSG:{item.get('target_srid', 25832)}", style=_BODY_CELL),
            html.Td(item.get("source_filename", ""), style={**_BODY_CELL, "maxWidth": "220px", "overflowWrap": "anywhere"}),
            html.Td(item.get("imported_by_username") or "—", style=_BODY_CELL),
            html.Td(item.get("imported_at", ""), style={**_BODY_CELL, "whiteSpace": "nowrap"}),
        ], style={"background": "#ffffff" if item.get("is_active") and not item.get("is_suppressed") else "#fcfcfd"}))
    return rows


def _feature_rows(records: list[dict]):
    if not records:
        return [html.Tr(html.Td("No coverage features are available for this page.", colSpan=5, style={**_BODY_CELL, "textAlign": "center", "padding": "18px", "color": "#64748b"}))]
    rows = []
    for item in records:
        attrs = item.get("attributes") or {}
        attr_text = json.dumps(attrs, ensure_ascii=False, sort_keys=True) if attrs else "—"
        rows.append(html.Tr([
            html.Td(str(item.get("source_feature_key") or ""), style=_BODY_CELL),
            html.Td(str(item.get("feature_label") or ""), style=_BODY_CELL),
            html.Td(f"{int(item.get('assigned_count') or 0):,}", style={**_BODY_CELL, "fontVariantNumeric": "tabular-nums"}),
            html.Td(context_breakdown_label(item.get("context_breakdown")), style={**_BODY_CELL, "maxWidth": "300px", "whiteSpace": "normal"}),
            html.Td(attr_text[:500], style={**_BODY_CELL, "maxWidth": "330px", "overflowWrap": "anywhere", "color": "#64748b"}),
        ]))
    return rows


def create_admin_coverage_layout(
    *,
    layers: list[dict],
    admin_username: str,
    csrf_token: str,
    target_srid: int = 25832,
    selected_layer_id: str | None = None,
    initial_map_bounds=None,
    students: list[dict] | None = None,
):
    management_options = [
        {"label": f"{item['layer_name']} · v{item['version']} · " + ("Suppressed" if item.get("is_suppressed") else "Active" if item.get("is_active") else "Archived"), "value": str(item["coverage_layer_id"])}
        for item in layers
    ]
    analysis_layers = [item for item in layers if item.get("is_active") and not item.get("is_suppressed")]
    analysis_options = [{"label": f"{item['layer_name']} · v{item['version']}", "value": str(item["coverage_layer_id"])} for item in analysis_layers]
    if selected_layer_id is None and analysis_options:
        selected_layer_id = analysis_options[0]["value"]
    managed_id = management_options[0]["value"] if management_options else None
    coverage_ns = Namespace("coverageMap", "handlers")
    student_options = [
        {
            "label": f"{item.get('username', 'Student')} · {item.get('email', '')}" + (" · inactive" if not item.get("is_active", True) else ""),
            "value": str(item["user_id"]),
            "disabled": not bool(item.get("is_active", True)),
        }
        for item in (students or [])
    ]

    upload_card = html.Section(
        style=_CARD_STYLE,
        children=[
            html.H2("Import a polygon coverage layer", style={"fontSize": "16px", "margin": "0 0 6px"}),
            html.P("Validate once, then publish the prepared import as a new immutable version. Older versions are retained.", style={"fontSize": "12px", "lineHeight": "1.5", "color": "#64748b", "margin": "0 0 14px"}),
            html.Div([
                html.Label("Coverage layer name", style=_LABEL_STYLE),
                dcc.Input(id="coverage-layer-name", type="text", maxLength=160, placeholder="e.g. Danish 1 km grid", value="", style=_INPUT_STYLE),
            ], style={"marginBottom": "12px"}),
            html.Div([
                html.Label("Source file", style=_LABEL_STYLE),
                dcc.Upload(
                    id="coverage-file-upload",
                    children=html.Div([html.Span("Drag and drop a file here, or "), html.A("browse", style={"fontWeight": "700", "color": "#1d4ed8"})]),
                    accept=".gpkg,.geojson,.json,.zip", multiple=False,
                    style={"width": "100%", "boxSizing": "border-box", "padding": "17px 12px", "border": "1px dashed #94a3b8", "borderRadius": "8px", "background": "#f8fafc", "textAlign": "center", "fontSize": "13px", "cursor": "pointer"},
                ),
                html.Div(id="coverage-upload-filename", style={"fontSize": "11px", "color": "#64748b", "marginTop": "6px"}),
            ], style={"marginBottom": "12px"}),
            html.Div([
                html.Label("Notes (optional)", style=_LABEL_STYLE),
                dcc.Textarea(id="coverage-layer-notes", maxLength=2000, placeholder="Source, dataset date, scale, intended use…", style={**_INPUT_STYLE, "minHeight": "64px", "resize": "vertical"}),
            ], style={"marginBottom": "14px"}),
            html.Div([
                html.Button("1. Validate and prepare", id="coverage-validate-button", n_clicks=0, style={**_BUTTON_STYLE, "background": "#e2e8f0", "color": "#1e293b"}),
                html.Button("2. Publish coverage layer", id="coverage-publish-button", n_clicks=0, disabled=True, style={**_BUTTON_STYLE, "background": "#1d4ed8", "color": "#ffffff", "marginLeft": "8px"}),
            ], style={"display": "flex", "flexWrap": "wrap", "gap": "6px", "alignItems": "center"}),
            html.Div(id="coverage-publish-loading", children=[html.Span(className="coverage-spinner"), html.Span("Publishing prepared features to the database. Please do not click again.")], style={"display": "none", "alignItems": "center", "gap": "10px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "12px"}),
            dcc.Loading(html.Div(id="coverage-validation-report", style={"marginTop": "14px"}), type="circle"),
            html.Div(id="coverage-publish-status", style={"marginTop": "10px", "fontSize": "12px"}),
            dcc.Store(id="coverage-validation-state", data=None),
            dcc.Store(id="coverage-published-event", data=None),
            dcc.Store(id="coverage-publishing-state", data=False),
        ],
    )

    registry_card = html.Section(
        style={**_CARD_STYLE, "marginTop": "16px"},
        children=[
            html.Div([
                html.Div([
                    html.H2("Coverage registry", style={"fontSize": "16px", "margin": "0 0 4px"}),
                    html.P("Versions are retained independently. Suppression hides a version from analysis without deleting its data.", style={"fontSize": "12px", "color": "#64748b", "margin": "0"}),
                ]),
                html.Button("Refresh", id="coverage-refresh-button", n_clicks=0, style={**_BUTTON_STYLE, "background": "#f1f5f9", "color": "#334155"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "12px", "marginBottom": "12px"}),
            html.Div(style={"overflowX": "auto", "border": "1px solid #e2e8f0", "borderRadius": "8px"}, children=html.Table([
                html.Thead(html.Tr([html.Th(label, style=_HEADER_CELL) for label in ("Layer", "Version", "Status", "Stored / expected features", "Format", "Source CRS", "Storage CRS", "Filename", "Imported by", "Imported")])),
                html.Tbody(_registry_rows(layers), id="coverage-registry-body"),
            ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"})),
            html.Div([
                html.Div([
                    html.Label("Select a coverage version", style=_LABEL_STYLE),
                    dcc.Dropdown(id="coverage-management-layer", options=management_options, value=managed_id, clearable=False, placeholder="Select a coverage version"),
                ], style={"flex": "1 1 330px", "minWidth": "240px"}),
                html.Div([
                    html.Button("Suppress", id="coverage-suppress-button", n_clicks=0, style={**_BUTTON_STYLE, "background": "#ffedd5", "color": "#9a3412"}),
                    html.Button("Reactivate / make active", id="coverage-reactivate-button", n_clicks=0, disabled=True, style={**_BUTTON_STYLE, "background": "#dbeafe", "color": "#1d4ed8", "marginLeft": "6px"}),
                    html.Button("Delete permanently", id="coverage-delete-button", n_clicks=0, style={**_BUTTON_STYLE, "background": "#fee2e2", "color": "#991b1b", "marginLeft": "6px"}),
                ], style={"display": "flex", "flexWrap": "wrap", "alignItems": "center"}),
            ], style={"display": "flex", "alignItems": "end", "flexWrap": "wrap", "gap": "12px", "marginTop": "14px"}),
            html.Div(id="coverage-management-status", style={"fontSize": "12px", "marginTop": "9px", "color": "#475569"}),
            html.Div(
                id="coverage-delete-dialog", className="coverage-modal-backdrop",
                role="presentation", style={"display": "none"},
                children=html.Div(
                    className="coverage-modal-card", role="dialog", **{"aria-modal": "true", "aria-labelledby": "coverage-delete-title"},
                    children=[
                        html.Button("×", id="coverage-delete-cancel-x", n_clicks=0, className="coverage-modal-close", **{"aria-label": "Cancel deletion"}),
                        html.H3("Delete coverage version?", id="coverage-delete-title", style={"fontSize": "17px", "margin": "0 28px 10px 0", "color": "#172033"}),
                        html.Div(id="coverage-delete-message", style={"fontSize": "13px", "lineHeight": "1.55", "color": "#475569"}),
                        html.Div([
                            html.Button("Cancel", id="coverage-delete-cancel", n_clicks=0, style={**_BUTTON_STYLE, "background": "#f1f5f9", "color": "#334155"}),
                            html.Button("Delete permanently", id="coverage-delete-confirm-button", n_clicks=0, style={**_BUTTON_STYLE, "background": "#b91c1c", "color": "#ffffff"}),
                        ], style={"display": "flex", "justifyContent": "flex-end", "gap": "8px", "marginTop": "20px"}),
                    ],
                ),
            ),
            dcc.Store(id="coverage-delete-target", data=None),
        ],
    )

    coverage_map_controls = create_layers_control("coverage-map-layer-control")
    coverage_map_controls[0].children = [
        *list(coverage_map_controls[0].children or []),
        dl.Overlay(
            dl.GeoJSON(id="coverage-polygons", data=_EMPTY_FC, clickData=None,
                       style=coverage_ns("polygonStyle"), onEachFeature=coverage_ns("onEachPolygon"),
                       hideout={"selected_feature_id": None}),
            name="Coverage polygons", checked=True,
        ),
        dl.Overlay(
            dl.GeoJSON(id="coverage-gcp-points", data=_EMPTY_FC,
                       pointToLayer=coverage_ns("pointToLayer"), onEachFeature=coverage_ns("onEachGcp")),
            name="GCP assignment points", checked=True,
        ),
    ]

    map_card = html.Section(
        style={**_CARD_STYLE, "marginTop": "16px"},
        children=[
            html.Div([
                html.Div([
                    html.H2("Coverage map", style={"fontSize": "16px", "margin": "0 0 4px"}),
                    html.P("Polygons are loaded for the current map viewport. GCPs are coloured by their assignment outcome.", style={"fontSize": "12px", "color": "#64748b", "margin": "0"}),
                ], style={"flex": "1"}),
                html.Div([
                    html.Label("Active coverage version", style=_LABEL_STYLE),
                    dcc.Dropdown(id="coverage-analysis-layer", options=analysis_options, value=selected_layer_id, clearable=False, placeholder="Select an active coverage version", style={"minWidth": "280px"}),
                ], style={"flex": "0 1 380px"}),
            ], style={"display": "flex", "alignItems": "end", "justifyContent": "space-between", "gap": "14px", "flexWrap": "wrap", "marginBottom": "12px"}),
            dl.Map(
                id="coverage-map", center=[56.15, 10.20], zoom=7, bounds=initial_map_bounds,
                children=[
                    *coverage_map_controls,
                ],
                style={"width": "100%", "height": "590px", "borderRadius": "8px", "overflow": "hidden"},
            ),
            html.Div(id="coverage-map-status", style={"fontSize": "11px", "color": "#64748b", "marginTop": "8px"}),
            html.Div([
                html.Span("● Assigned uniquely", style={"color": "#15803d", "fontSize": "11px", "marginRight": "14px"}),
                html.Span("● Uncovered", style={"color": "#d97706", "fontSize": "11px", "marginRight": "14px"}),
                html.Span("● Multiple matches", style={"color": "#dc2626", "fontSize": "11px"}),
            ], style={"marginTop": "5px"}),
        ],
    )

    assignment_card = html.Section(
        style={**_CARD_STYLE, "marginTop": "16px"},
        children=[
            html.H2("Student work allocation", style={"fontSize": "16px", "margin": "0 0 5px"}),
            html.P("Click one polygon on the map, then select the students responsible for it. Saving replaces the selected polygon's assignment list. This is work guidance only; it does not restrict where students may create GCPs.", style={"fontSize": "12px", "lineHeight": "1.5", "color": "#64748b", "margin": "0 0 12px"}),
            html.Div(id="coverage-selected-feature-label", children="No polygon selected. Click a polygon on the map to manage its student assignments.", style={"fontSize": "12px", "fontWeight": "650", "color": "#334155", "marginBottom": "8px"}),
            dcc.Dropdown(
                id="coverage-assignment-students", options=student_options, value=[], multi=True,
                placeholder="Select one or more students", clearable=True,
            ),
            html.Div([
                html.Button("Save assignments", id="coverage-assignment-save", n_clicks=0, disabled=True,
                            style={**_BUTTON_STYLE, "background": "#1d4ed8", "color": "#ffffff", "marginTop": "10px"}),
                html.Div([html.Span(className="coverage-spinner"), html.Span("Saving polygon assignments…")],
                         id="coverage-assignment-loading", style={"display": "none", "alignItems": "center", "gap": "9px", "fontSize": "12px", "color": "#1d4ed8", "marginTop": "10px"}),
            ]),
            html.Div(id="coverage-assignment-save-status", style={"fontSize": "12px", "marginTop": "8px"}),
        ],
    )

    analysis_card = html.Section(
        style={**_CARD_STYLE, "marginTop": "16px"},
        children=[
            html.Div([
                html.Div([
                    html.H2("Spatial assignment and statistics", style={"fontSize": "16px", "margin": "0 0 4px"}),
                    html.P("A GCP is assigned only when exactly one polygon covers its reference coordinate. Zero matches are uncovered; two or more are multiple matches.", style={"fontSize": "12px", "color": "#64748b", "margin": "0", "lineHeight": "1.5"}),
                ], style={"flex": "1"}),
                html.Button("Run unique assignment", id="coverage-run-analysis", n_clicks=0, style={**_BUTTON_STYLE, "background": "#1d4ed8", "color": "#ffffff"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"}),
            html.Div([html.Span(className="coverage-spinner"), html.Span("Calculating GCP-to-polygon relationships and statistics…")], id="coverage-analysis-loading", style={"display": "none", "alignItems": "center", "gap": "10px", "fontSize": "12px", "color": "#1d4ed8", "marginBottom": "10px"}),
            html.Div(id="coverage-assignment-summary", children="Run an assignment to calculate the coverage summary."),
            html.Div(id="coverage-analysis-status", style={"fontSize": "12px", "color": "#475569", "marginTop": "10px"}),
            html.Div([
                html.H3("Coverage feature statistics", style={"fontSize": "14px", "margin": "16px 0 8px"}),
                html.Div(style={"overflowX": "auto", "border": "1px solid #e2e8f0", "borderRadius": "8px"}, children=html.Table([
                    html.Thead(html.Tr([html.Th(label, style=_HEADER_CELL) for label in ("Source feature key", "Feature label", "Uniquely assigned GCPs", "Context breakdown", "Attributes (preview)") ])),
                    html.Tbody([html.Tr(html.Td("Run the assignment to load feature statistics.", colSpan=5, style={**_BODY_CELL, "textAlign": "center", "padding": "18px", "color": "#64748b"}))], id="coverage-feature-table-body"),
                ], style={"width": "100%", "borderCollapse": "collapse"})),
                html.Div([
                    html.Button("Previous", id="coverage-feature-prev", n_clicks=0, style={**_BUTTON_STYLE, "background": "#f1f5f9", "color": "#334155"}),
                    html.Span("Page 0 of 0", id="coverage-feature-page-label", style={"fontSize": "11px", "color": "#64748b", "padding": "0 10px"}),
                    html.Button("Next", id="coverage-feature-next", n_clicks=0, style={**_BUTTON_STYLE, "background": "#f1f5f9", "color": "#334155"}),
                ], style={"display": "flex", "alignItems": "center", "justifyContent": "center", "marginTop": "10px"}),
                html.Div([
                    html.Button("Export feature statistics CSV", id="coverage-export-features", n_clicks=0, disabled=True, style={**_BUTTON_STYLE, "background": "#e0f2fe", "color": "#075985"}),
                    html.Button("Export GCP assignment CSV", id="coverage-export-assignments", n_clicks=0, disabled=True, style={**_BUTTON_STYLE, "background": "#e0f2fe", "color": "#075985", "marginLeft": "7px"}),
                ], style={"marginTop": "12px"}),
            ]),
            dcc.Store(id="coverage-feature-page", data=0),
            dcc.Store(id="coverage-analysis-state", data=None),
            dcc.Download(id="coverage-feature-download"),
            dcc.Download(id="coverage-assignment-download"),
        ],
    )

    children = [
        html.Div([
            html.Div("Import formats: GeoPackage, GeoJSON and zipped Shapefile", style={"fontWeight": "700", "fontSize": "12px", "color": "#334155"}),
            html.Div(
                f"Storage CRS: EPSG:{target_srid}. Only valid 2D Polygon and MultiPolygon features are accepted. No automatic geometry repair is performed. GeoJSON without CRS metadata follows its standard EPSG:4326 convention; other formats must declare a CRS.",
                style={"fontSize": "12px", "color": "#64748b", "marginTop": "4px", "lineHeight": "1.5"},
            ),
        ], style={"padding": "12px 14px", "border": "1px solid #cbd5e1", "borderRadius": "9px", "background": "#f8fafc", "marginBottom": "14px"}),
        upload_card,
        registry_card,
        map_card,
        assignment_card,
        analysis_card,
        dcc.Store(id="coverage-selected-feature", data=None),
        dcc.Store(id="coverage-assignment-saving", data=False),
        dcc.Store(id="coverage-ui-refresh", data=None),
    ]
    return create_page_shell(
        title="Coverage & Statistics",
        subtitle="Manage polygon coverage datasets, assign GCPs spatially and inspect feature-level statistics.",
        admin_username=admin_username,
        csrf_token=csrf_token,
        active_page="coverage",
        children=children,
    )

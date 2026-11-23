from __future__ import annotations

from dash import dcc, html

from ui.admin_nav import create_page_shell


_CARD_STYLE = {
    "background": "#ffffff",
    "border": "1px solid #dbe2ea",
    "borderRadius": "12px",
    "padding": "16px",
    "boxShadow": "0 1px 3px rgba(15,23,42,0.04)",
}
_LABEL_STYLE = {
    "display": "block",
    "fontSize": "12px",
    "fontWeight": "700",
    "color": "#334155",
    "marginBottom": "6px",
}
_INPUT_STYLE = {
    "width": "100%",
    "boxSizing": "border-box",
    "padding": "9px 10px",
    "border": "1px solid #cbd5e1",
    "borderRadius": "7px",
    "fontSize": "13px",
}
_BUTTON_STYLE = {
    "border": "0",
    "borderRadius": "7px",
    "padding": "9px 13px",
    "fontSize": "12px",
    "fontWeight": "700",
    "cursor": "pointer",
}


def _registry_rows(layers: list[dict]):
    if not layers:
        return [html.Tr(html.Td(
            "No coverage layers have been imported yet.",
            colSpan=9,
            style={"padding": "18px", "textAlign": "center", "color": "#64748b"},
        ))]

    rows = []
    for item in layers:
        status = "Active" if item.get("is_active") else "Archived version"
        status_color = "#166534" if item.get("is_active") else "#64748b"
        rows.append(html.Tr([
            html.Td(item.get("layer_name", ""), style={"fontWeight": "700"}),
            html.Td(f"v{item.get('version', '')}"),
            html.Td(status, style={"color": status_color, "fontWeight": "700"}),
            html.Td(f"{item.get('stored_feature_count', 0):,} / {item.get('feature_count', 0):,}"),
            html.Td(item.get("source_format", "")),
            html.Td(item.get("source_crs", "")),
            html.Td(f"EPSG:{item.get('target_srid', 25832)}"),
            html.Td(item.get("source_filename", ""), style={"maxWidth": "230px", "overflowWrap": "anywhere"}),
            html.Td(item.get("imported_at", "")),
        ], style={"borderBottom": "1px solid #e2e8f0"}))
    return rows


def create_admin_coverage_layout(
    *,
    layers: list[dict],
    admin_username: str,
    csrf_token: str,
    target_srid: int = 25832,
):
    upload_card = html.Section(
        style=_CARD_STYLE,
        children=[
            html.H2("Import a polygon coverage layer", style={"fontSize": "16px", "margin": "0 0 6px"}),
            html.P(
                "Upload one polygon dataset, validate it, then publish it as a versioned coverage layer. "
                "Existing versions are retained.",
                style={"fontSize": "12px", "lineHeight": "1.5", "color": "#64748b", "margin": "0 0 14px"},
            ),
            html.Div([
                html.Label("Coverage layer name", style=_LABEL_STYLE),
                dcc.Input(
                    id="coverage-layer-name", type="text", maxLength=160,
                    placeholder="e.g. Danish 1 km grid", value="", style=_INPUT_STYLE,
                ),
            ], style={"marginBottom": "12px"}),
            html.Div([
                html.Label("Source file", style=_LABEL_STYLE),
                dcc.Upload(
                    id="coverage-file-upload",
                    children=html.Div([
                        html.Span("Drag and drop a file here, or "),
                        html.A("browse", style={"fontWeight": "700", "color": "#1d4ed8"}),
                    ]),
                    accept=".gpkg,.geojson,.json,.zip",
                    multiple=False,
                    style={
                        "width": "100%", "boxSizing": "border-box", "padding": "17px 12px",
                        "border": "1px dashed #94a3b8", "borderRadius": "8px",
                        "background": "#f8fafc", "textAlign": "center", "fontSize": "13px",
                        "cursor": "pointer",
                    },
                ),
                html.Div(id="coverage-upload-filename", style={"fontSize": "11px", "color": "#64748b", "marginTop": "6px"}),
            ], style={"marginBottom": "12px"}),
            html.Div([
                html.Label("Notes (optional)", style=_LABEL_STYLE),
                dcc.Textarea(
                    id="coverage-layer-notes", maxLength=2000,
                    placeholder="Source, dataset date, scale, intended use…",
                    style={**_INPUT_STYLE, "minHeight": "64px", "resize": "vertical"},
                ),
            ], style={"marginBottom": "14px"}),
            html.Div([
                html.Button(
                    "1. Validate file", id="coverage-validate-button", n_clicks=0,
                    style={**_BUTTON_STYLE, "background": "#e2e8f0", "color": "#1e293b"},
                ),
                html.Button(
                    "2. Publish coverage layer", id="coverage-publish-button", n_clicks=0,
                    disabled=True,
                    style={**_BUTTON_STYLE, "background": "#1d4ed8", "color": "#ffffff", "marginLeft": "8px"},
                ),
            ], style={"display": "flex", "flexWrap": "wrap", "gap": "6px", "alignItems": "center"}),
            dcc.Loading(html.Div(id="coverage-validation-report", style={"marginTop": "14px"}), type="circle"),
            html.Div(id="coverage-publish-status", style={"marginTop": "10px", "fontSize": "12px"}),
            dcc.Store(id="coverage-validation-state", data=None),
        ],
    )

    registry_card = html.Section(
        style={**_CARD_STYLE, "marginTop": "16px"},
        children=[
            html.Div([
                html.Div([
                    html.H2("Coverage registry", style={"fontSize": "16px", "margin": "0 0 4px"}),
                    html.P(
                        "Each import is stored as an immutable version. Only one version per layer name is active.",
                        style={"fontSize": "12px", "color": "#64748b", "margin": "0"},
                    ),
                ]),
                html.Button(
                    "Refresh", id="coverage-refresh-button", n_clicks=0,
                    style={**_BUTTON_STYLE, "background": "#f1f5f9", "color": "#334155"},
                ),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "12px", "marginBottom": "12px"}),
            html.Div(
                style={"overflowX": "auto", "border": "1px solid #e2e8f0", "borderRadius": "8px"},
                children=html.Table([
                    html.Thead(html.Tr([
                        html.Th(label, style={"textAlign": "left", "fontSize": "11px", "padding": "10px", "background": "#f8fafc", "whiteSpace": "nowrap"})
                        for label in (
                            "Layer", "Version", "Status", "Stored / expected features",
                            "Format", "Source CRS", "Storage CRS", "Filename", "Imported",
                        )
                    ])),
                    html.Tbody(_registry_rows(layers), id="coverage-registry-body"),
                ], style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"}),
            ),
        ],
    )

    children = [
        html.Div([
            html.Div([
                html.Div("Import formats: GeoPackage, GeoJSON and zipped Shapefile", style={"fontWeight": "700", "fontSize": "12px", "color": "#334155"}),
                html.Div(
                    f"Storage CRS: EPSG:{target_srid}. Only 2D Polygon and MultiPolygon geometries are accepted. "
                    "Empty/invalid geometry and mixed types are rejected. GeoJSON without CRS metadata follows "
                    "the standard EPSG:4326 convention; other formats must declare a CRS.",
                    style={"fontSize": "12px", "color": "#64748b", "marginTop": "4px", "lineHeight": "1.5"},
                ),
            ], style={"padding": "12px 14px", "border": "1px solid #cbd5e1", "borderRadius": "9px", "background": "#f8fafc", "marginBottom": "14px"}),
            upload_card,
            registry_card,
            html.Div(
                "This increment covers registry and import only. Map display, GCP-to-polygon assignment and statistics are the next implementation step.",
                style={"fontSize": "11px", "color": "#64748b", "marginTop": "12px"},
            ),
        ])
    ]

    return create_page_shell(
        title="Coverage & Statistics",
        subtitle="Manage polygon coverage datasets independently of the GCP collection workspace.",
        admin_username=admin_username,
        csrf_token=csrf_token,
        active_page="coverage",
        children=children,
    )

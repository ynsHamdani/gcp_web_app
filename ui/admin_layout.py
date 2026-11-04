from __future__ import annotations

from dash import dcc, html
import dash_ag_grid as dag

from maps.admin_gcp import build_admin_gcp_row
from services.admin_layer_summary import summarize_unavailable_layers
from ui.admin_nav import create_workspace_header


_BASE_BUTTON = {
    "padding": "7px 10px",
    "border": "1px solid #cbd5e1",
    "borderRadius": "7px",
    "background": "#ffffff",
    "cursor": "pointer",
    "fontSize": "12px",
    "whiteSpace": "nowrap",
}
_PRIMARY_BUTTON = {
    **_BASE_BUTTON,
    "background": "#1d4ed8",
    "border": "1px solid #1d4ed8",
    "color": "white",
}
_DANGER_BUTTON = {
    **_BASE_BUTTON,
    "color": "#b91c1c",
    "border": "1px solid #fecaca",
}
_DISABLED_BUTTON = {**_BASE_BUTTON, "opacity": 0.55, "cursor": "not-allowed"}


def _unavailable_note(unavailable: list[str] | None):
    summary = summarize_unavailable_layers(unavailable)
    if summary["total"] == 0:
        return html.Span(
            "All registered uploaded rasters are currently available.",
            style={"fontSize": "11px", "color": "#166534"},
        )
    detail_groups = []
    for kind, label in (("reference", "Reference"), ("historical", "Historical"), ("other", "Other")):
        values = summary["groups"].get(kind, [])
        if values:
            detail_groups.append(
                html.Div(
                    [
                        html.Strong(f"{label} ({len(values)})"),
                        html.Ul([html.Li(value) for value in values]),
                    ],
                    style={"fontSize": "11px", "color": "#7c2d12"},
                )
            )
    return html.Details(
        [
            html.Summary(
                f"{summary['total']} unavailable raster(s) · {summary['reference']} reference · {summary['historical']} historical",
                style={"cursor": "pointer", "fontSize": "11px", "fontWeight": "600", "color": "#92400e"},
            ),
            html.Div(detail_groups, style={"padding": "6px 4px 0"}),
        ],
        open=False,
        style={"marginTop": "7px"},
    )


def create_admin_layout(
    *,
    reference_map,
    historical_map,
    records: list[dict] | None = None,
    historical_options: list[dict] | None = None,
    contributor_options: list[dict] | None = None,
    layer_state: dict | None = None,
    reference_layer_options: list[dict] | None = None,
    historical_available_options: list[dict] | None = None,
    selected_reference_layer_id: str | None = None,
    selected_historical_layer_id: str | None = None,
    unavailable_layers: list[str] | None = None,
    csrf_token: str = "",
    admin_username: str = "Administrator",
):
    """Build a compact workspace with explicit load/zoom/activate controls."""

    records = records or []
    layer_state = layer_state or {}
    unavailable_layers = unavailable_layers or []
    historical_options = historical_options or []
    contributor_options = contributor_options or []
    reference_layer_options = reference_layer_options or []
    historical_available_options = historical_available_options or []

    table_columns = [
        {"field": "gcp_id", "headerName": "GCP", "width": 105},
        {"field": "student_username", "headerName": "Contributor", "width": 155},
        {"field": "contributor_role", "headerName": "Role", "width": 95},
        {"field": "historical_layer_name", "headerName": "Historical layer", "width": 190},
        {"field": "reference_layer_name", "headerName": "Reference layer", "width": 190},
        {"field": "offset_m", "headerName": "Offset (m)", "width": 105},
        {"field": "reference_raster_available", "headerName": "Reference raster", "width": 125},
        {"field": "historical_raster_available", "headerName": "Historical raster", "width": 130},
        {"field": "status", "headerName": "Status", "width": 100},
        {"field": "recorded_at", "headerName": "Recorded", "width": 180},
    ]
    table = dag.AgGrid(
        id="admin-gcp-table",
        rowData=[build_admin_gcp_row(record) for record in records],
        columnDefs=table_columns,
        defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 90},
        dashGridOptions={
            "animateRows": False,
            "rowSelection": {"mode": "singleRow"},
            "suppressRowClickSelection": False,
        },
        style={"height": "265px", "width": "100%"},
    )

    card_style = {
        "minWidth": "0",
        "border": "1px solid #dbe2ea",
        "borderRadius": "10px",
        "background": "#ffffff",
        "padding": "10px",
    }
    field_label = {"fontWeight": "600", "fontSize": "12px", "display": "block", "marginBottom": "5px"}
    muted = {"fontSize": "11px", "color": "#64748b"}
    panel_style = {
        "background": "#f8fafc",
        "border": "1px solid #e2e8f0",
        "borderRadius": "8px",
        "padding": "10px",
        "minWidth": "0",
    }
    upload_box = {
        "border": "1px dashed #94a3b8",
        "borderRadius": "8px",
        "padding": "9px",
        "background": "#ffffff",
        "textAlign": "center",
        "fontSize": "12px",
        "color": "#334155",
        "cursor": "pointer",
    }
    basemap_id = str(layer_state.get("basemap_reference_layer_id") or "")
    selected_ref_is_basemap = bool(selected_reference_layer_id and basemap_id and str(selected_reference_layer_id) == basemap_id)
    initial_loaded = {
        "reference_loaded_db_layer_id": str(selected_reference_layer_id) if selected_reference_layer_id else None,
        "historical_loaded_db_layer_id": str(selected_historical_layer_id) if selected_historical_layer_id else None,
        # OpenStreetMap is already present as the map base layer. It is a valid
        # reference support and is active immediately; uploaded rasters still
        # require the explicit Load + Zoom actions.
        "reference_db_layer_id": str(selected_reference_layer_id) if selected_ref_is_basemap else None,
        "historical_db_layer_id": None,
    }
    collection_ready = bool(initial_loaded["reference_db_layer_id"] and initial_loaded["historical_db_layer_id"])

    return html.Div(
        className="app-container admin-container",
        style={
            "maxWidth": "1800px",
            "margin": "0 auto",
            "padding": "8px 16px 18px",
            "background": "#f5f7fb",
            "height": "100vh",
            "overflow": "hidden",
            "boxSizing": "border-box",
        },
        children=[
            create_workspace_header(admin_username=admin_username, csrf_token=csrf_token),
            html.Main(
                id="admin-workspace-scroll",
                style={
                    "position": "fixed", "top": "72px", "bottom": "0", "left": "0", "right": "0",
                    "overflowY": "auto", "overflowX": "hidden", "overscrollBehavior": "contain",
                },
                children=[
                    html.Div(
                        style={"maxWidth": "1800px", "margin": "0 auto", "padding": "8px 16px 18px", "boxSizing": "border-box"},
                        children=[

            # Layer manager is the main starting point. Existing layers and
            # upload controls are grouped here; upload is collapsed by default.
            html.Details(
                id="admin-add-gcp-panel",
                open=True,
                style={**card_style, "marginTop": "10px", "marginBottom": "10px", "scrollMarginTop": "75px"},
                children=[
                    html.Summary("Add a GCP · Layer manager", style={"fontSize": "14px", "fontWeight": "750", "cursor": "pointer", "color": "#172033", "marginBottom": "9px"}),
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "10px", "flexWrap": "wrap", "marginBottom": "8px"},
                        children=[
                            html.H3("Add a GCP · Layer manager", style={"margin": "0", "fontSize": "15px", "color": "#172033"}),
                            html.Span("Select → Load → Zoom to activate for collection", style=muted),
                        ],
                    ),
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(260px, 1fr))", "gap": "10px"},
                        children=[
                            html.Div(
                                style=panel_style,
                                children=[
                                    html.Div("Option A · Reference layer", style={"fontWeight": "700", "fontSize": "12px", "marginBottom": "6px"}),
                                    html.Label("Select reference layer", style=field_label),
                                    dcc.Dropdown(
                                        id="admin-reference-existing-select",
                                        options=reference_layer_options,
                                        value=selected_reference_layer_id,
                                        searchable=True,
                                        clearable=False,
                                        placeholder="Choose an available reference layer",
                                    ),
                                    html.Div(
                                        style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "marginTop": "7px"},
                                        children=[
                                            html.Button("Load reference", id="admin-load-reference-layer", n_clicks=0, style=_PRIMARY_BUTTON),
                                            html.Button("Zoom reference", id="admin-zoom-reference-layer", n_clicks=0, style=_BASE_BUTTON),
                                        ],
                                    ),
                                    html.Div(id="admin-reference-layer-indicator", children=("Loaded · press Zoom to activate for GCP collection" if selected_reference_layer_id else "No available reference layer selected"), style={**muted, "marginTop": "6px"}),
                                ],
                            ),
                            html.Div(
                                style=panel_style,
                                children=[
                                    html.Div("Option A · Historical layer", style={"fontWeight": "700", "fontSize": "12px", "marginBottom": "6px"}),
                                    html.Label("Select historical layer", style=field_label),
                                    dcc.Dropdown(
                                        id="admin-historical-existing-select",
                                        options=historical_available_options,
                                        value=selected_historical_layer_id,
                                        searchable=True,
                                        clearable=False,
                                        placeholder="Choose an available historical layer",
                                    ),
                                    html.Div(
                                        style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "marginTop": "7px"},
                                        children=[
                                            html.Button("Load historical", id="admin-load-historical-layer", n_clicks=0, style=_PRIMARY_BUTTON),
                                            html.Button("Zoom historical", id="admin-zoom-historical-layer", n_clicks=0, style=_BASE_BUTTON),
                                        ],
                                    ),
                                    html.Div(id="admin-historical-layer-indicator", children=("Loaded · press Zoom to activate for GCP collection" if selected_historical_layer_id else "No available historical layer selected"), style={**muted, "marginTop": "6px"}),
                                ],
                            ),
                        ],
                    ),
                    html.Details(
                        style={**panel_style, "marginTop": "8px"},
                        open=False,
                        children=[
                            html.Summary("Option B · Upload new GeoTIFF layers", style={"fontWeight": "700", "fontSize": "12px", "cursor": "pointer"}),
                            html.Div("Upload a reference GeoTIFF, a historical GeoTIFF, or both. Files use the existing COG conversion and registration pipeline.", style={**muted, "margin": "6px 0 8px"}),
                            html.Div(
                                style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(220px, 1fr))", "gap": "10px"},
                                children=[
                                    html.Div(
                                        [
                                            html.Label("Reference GeoTIFF", style=field_label),
                                            dcc.Upload(
                                                id="admin-reference-upload",
                                                children=html.Div([html.Div("Choose or drop reference .tif/.tiff"), html.Div(id="admin-reference-upload-filename", children="No file selected", style={"fontSize": "11px", "color": "#64748b", "marginTop": "4px"})], style=upload_box),
                                                accept=".tif,.tiff,image/tiff",
                                                multiple=False,
                                            ),
                                        ]
                                    ),
                                    html.Div(
                                        [
                                            html.Label("Historical GeoTIFF", style=field_label),
                                            dcc.Upload(
                                                id="admin-historical-upload",
                                                children=html.Div([html.Div("Choose or drop historical .tif/.tiff"), html.Div(id="admin-historical-upload-filename", children="No file selected", style={"fontSize": "11px", "color": "#64748b", "marginTop": "4px"})], style=upload_box),
                                                accept=".tif,.tiff,image/tiff",
                                                multiple=False,
                                            ),
                                        ]
                                    ),
                                ],
                            ),
                            html.Div(
                                style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap", "marginTop": "8px"},
                                children=[
                                    html.Button("Upload selected file(s)", id="admin-upload-layers", n_clicks=0, style=_BASE_BUTTON),
                                    html.Span(id="admin-upload-status", children="No new files selected.", style=muted),
                                ],
                            ),
                        ],
                    ),
                    html.Div(id="admin-layer-load-status", children="Load each selected layer, then use its Zoom button to activate it for GCP collection.", role="status", style={"fontSize": "11px", "color": "#334155", "marginTop": "7px"}),
                    html.Div(id="admin-unavailable-layer-note", children=_unavailable_note(unavailable_layers)),
                ],
            ),

            html.Section(
                style={**card_style, "marginBottom": "10px"},
                children=[
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "7px", "flexWrap": "wrap"},
                        children=[
                            html.Strong("Collection", style={"fontSize": "12px"}),
                            html.Button("Add GCP", id="admin-add-gcp-button", n_clicks=0, disabled=not collection_ready, style=_PRIMARY_BUTTON if collection_ready else _DISABLED_BUTTON),
                            html.Button("Confirm GCP", id="admin-confirm-gcp-button", n_clicks=0, disabled=True, style=_BASE_BUTTON),
                            html.Button("Cancel", id="admin-cancel-gcp-button", n_clicks=0, disabled=True, style=_BASE_BUTTON),
                            html.Span("Click reference map; drag the historical marker to refine.", style=muted),
                        ],
                    ),
                    html.Div(id="admin-gcp-collection-status", children=("OpenStreetMap is active as the reference support. Load and Zoom a historical raster to enable collection." if selected_ref_is_basemap else "Activate one reference and one historical layer with their Zoom buttons to enable collection."), role="status", style={"fontSize": "11px", "color": "#334155", "marginTop": "6px"}),
                ],
            ),

            html.Details(
                id="admin-filter-panel",
                open=False,
                style={**card_style, "marginBottom": "10px", "scrollMarginTop": "75px"},
                children=[
                    html.Summary("Filter GCPs", style={"fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
                    html.Div(
                        style={"display": "grid", "gridTemplateColumns": "minmax(220px, 1fr) minmax(220px, 1fr) auto", "gap": "10px", "alignItems": "end", "marginTop": "9px"},
                        children=[
                            html.Div(
                                [
                                    html.Label("Contributor", style=field_label),
                                    dcc.Dropdown(id="admin-contributor-filter", options=[{"label": "All contributors", "value": "all"}, *contributor_options], value="all", clearable=False, searchable=True, placeholder="Select student or administrator"),
                                ]
                            ),
                            html.Div(
                                [
                                    html.Label("Historical layer", style=field_label),
                                    dcc.Dropdown(id="admin-historical-filter", options=[{"label": "All historical layers", "value": "all"}, *historical_options], value="all", clearable=False, searchable=True, placeholder="Select a historical layer"),
                                ]
                            ),
                            html.Div(
                                style={"display": "flex", "gap": "6px", "flexWrap": "wrap"},
                                children=[
                                    html.Button("Apply", id="admin-apply-filter", n_clicks=0, style=_PRIMARY_BUTTON),
                                    html.Button("Refresh", id="admin-refresh", n_clicks=0, style=_BASE_BUTTON),
                                    html.Button("Delete selected", id="admin-delete-gcp", n_clicks=0, style=_DANGER_BUTTON),
                                    html.Button("Export CSV", id="admin-export-gcps", n_clicks=0, style=_BASE_BUTTON),
                                    dcc.Download(id="admin-gcp-download"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(id="admin-gcp-status", children=f"Loaded {len(records)} GCP(s).", role="status", style={"fontSize": "11px", "color": "#334155", "marginTop": "7px"}),
                    html.Div(id="admin-raster-status", children="Raster availability is checked on Refresh.", role="status", style={"fontSize": "11px", "color": "#92400e", "marginTop": "4px"}),
                ],
            ),

            html.Section(
                id="admin-maps",
                style={"display": "grid", "gridTemplateColumns": "repeat(2, minmax(0, 1fr))", "gap": "10px", "marginBottom": "10px", "scrollMarginTop": "75px"},
                children=[
                    html.Div(
                        style=card_style,
                        children=[
                            html.Div(style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px"}, children=[html.H3("Reference map", style={"margin": "0", "fontSize": "14px"}), html.Span("Reference overlay", style=muted)]),
                            html.Div(
                                style={"display": "flex", "alignItems": "center", "gap": "10px", "margin": "4px 0 7px"},
                                children=[html.Label("Overlay opacity", style=muted), dcc.Slider(id="admin-reference-opacity", min=0, max=100, step=5, value=75, marks={0: "0%", 100: "100%"}, tooltip={"placement": "bottom", "always_visible": False})],
                            ),
                            html.Div(reference_map, style={"height": "350px", "width": "100%"}),
                        ],
                    ),
                    html.Div(
                        style=card_style,
                        children=[
                            html.Div(style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px"}, children=[html.H3("Historical map", style={"margin": "0", "fontSize": "14px"}), html.Span("Historical overlay", style=muted)]),
                            html.Div(
                                style={"display": "flex", "alignItems": "center", "gap": "10px", "margin": "4px 0 7px"},
                                children=[html.Label("Overlay opacity", style=muted), dcc.Slider(id="admin-historical-opacity", min=0, max=100, step=5, value=75, marks={0: "0%", 100: "100%"}, tooltip={"placement": "bottom", "always_visible": False})],
                            ),
                            html.Div(historical_map, style={"height": "350px", "width": "100%"}),
                        ],
                    ),
                ],
            ),

            html.Details(
                id="admin-records",
                open=False,
                style={**card_style, "scrollMarginTop": "75px"},
                children=[
                    html.Summary(f"GCP records · {len(records)} loaded", style={"fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
                    html.Div("Select a row to zoom both maps to that GCP and highlight its marker.", style={**muted, "margin": "7px 0"}),
                    table,
                ],
            ),

            # State shared by layer actions, viewport dispatcher, Step 1 filters,
            # and the administrator collection workflow.
            dcc.Store(id="admin-gcp-records", data=records),
            dcc.Store(id="admin-layer-state", data=layer_state),
            dcc.Store(id="admin-selection-layer-state", data=layer_state),
            dcc.Store(id="admin-loaded-layer-selection", data=initial_loaded),
            dcc.Store(id="admin-layer-viewport-request", data=None),
            dcc.Store(id="admin-gcp-viewport-request", data=None),
            dcc.Store(id="admin-viewport-applied", data=None),
            dcc.Store(id="admin-gcp-pending", data=None),
            dcc.Store(id="admin-gcp-collection-active", data=False),
            dcc.Store(id="admin-gcp-drag-event", data=None),
            dcc.Store(id="admin-gcp-collection-revision", data=0),
                        ],
                    ),
                ],
            ),
        ],
    )
